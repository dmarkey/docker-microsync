"""Docker Microsync

Usage:
  docker_microsync.py <path> <prefix_path> <base_image>\
  [--file-extensions=<csv_list>] [--timeout=<timeout>]
  docker_microsync.py -h | --help | --version

Options:
   --timeout=<timeout>  Time in seconds after the last \
change to build the new image [default: 0.5].
"""
import sys

import io
import tarfile
from docopt import docopt
from queue import Queue, Empty
from watchdog.events import FileSystemEventHandler, FileMovedEvent, \
    FileCreatedEvent, FileModifiedEvent, FileDeletedEvent
from watchdog.observers import Observer
import docker
import logging

logger = logging.getLogger(__name__)


class QueueFileSystemEventHandler(FileSystemEventHandler):
    def __init__(self, *args, outbound_queue=None, **kwargs):
        self.queue = outbound_queue
        super().__init__(*args, **kwargs)

    def on_any_event(self, event):
        self.queue.put(event)


def _tar_add_bytes(tar_file, filename, bytestring):
    if not isinstance(bytestring, bytes):
        bytestring = bytestring.encode('ascii')
    buff = io.BytesIO(bytestring)
    tarinfo = tarfile.TarInfo(filename)
    tarinfo.size = len(bytestring)
    tar_file.addfile(tarinfo, buff)


class DockerMicrosync(object):
    def __init__(self, path, prefix_path, base_image, file_extensions=None,
                 timeout=0.5):
        self.builds = 0
        self.path = path
        self.base_image = base_image
        if file_extensions:
            self.file_extensions = tuple(file_extensions)
        else:
            self.file_extensions = None

        self.timeout = timeout
        self.observer = Observer()
        self.outbound_queue = Queue()
        self.docker_client = docker.from_env()
        self.prefix_path = prefix_path
        self.stopping = False
        event_handler = QueueFileSystemEventHandler(
            outbound_queue=self.outbound_queue)
        self.observer.schedule(event_handler, self.path, recursive=True)

    def start(self):
        self.observer.start()
        while True:
            logger.info(
                "Starting to watch for changed files - {} "
                "second timeout.".format(
                    self.timeout))
            dockerfile = ["from {}".format(self.base_image)]
            tarbuffer = io.BytesIO()
            tf = tarfile.TarFile(fileobj=tarbuffer, mode='w')
            files_changed = False
            while True:
                if self.stopping:
                    return

                try:

                    event = self.outbound_queue.get(timeout=self.timeout)
                    if isinstance(event, FileMovedEvent):
                        if self._add_file(tf, dockerfile, event.dest_path):
                            files_changed = True
                    if isinstance(event, FileCreatedEvent):
                        if self._add_file(tf, dockerfile, event.src_path):
                            files_changed = True
                    if isinstance(event, FileModifiedEvent):
                        if self._add_file(tf, dockerfile, event.src_path):
                            files_changed = True
                    if isinstance(event, FileDeletedEvent):
                        if self._delete_file(dockerfile, event.src_path):
                            files_changed = True
                except Empty:
                    if files_changed:
                        logger.info("Building image.")
                        _tar_add_bytes(tf, "Dockerfile", "\n".join(dockerfile))
                        tarbuffer.seek(0)
                        image, _ = self.docker_client.images.build(
                            fileobj=tarbuffer,
                            custom_context=True,
                            tag=self.base_image)
                        logger.info("{} built, starting over.".format(
                            image))
                        self.builds += 1
                        break

    def stop(self):
        self.stopping = True
        self.observer.stop()

    def _delete_file(self, dockerfile, path):
        logger.info("Attempting to delete file {}".format(path))
        if self.file_extensions and not path.endswith(self.file_extensions):
            logger.info("File extension doesn't match, skipping")
            return False
        dockerfile_path = path[len(self.path) + 1:]
        logger.info("Deleting file {}".format(dockerfile_path))
        dockerfile.append(
            "run rm '{}' || exit 0\n".format(dockerfile_path)
        )
        return True

    def _add_file(self, tf, dockerfile, path):
        logger.info("Attempting to add file {}".format(path))
        if self.file_extensions and not path.endswith(self.file_extensions):
            logger.info("File extension doesn't match, skipping")
            return False
        try:
            f = open(path, "rb")
            dockerfile_path_from = path[len(self.path) + 1:]
            _tar_add_bytes(tf, dockerfile_path_from, f.read())

            dockerfile_to = "{}/{}".format(self.prefix_path,
                                           path[len(self.path) + 1:])
            logger.info("Adding to dockerfile, from {} to {}".format(
                dockerfile_path_from, dockerfile_to))
            dockerfile.append(
                "copy '{}' '{}'\n".format(dockerfile_path_from, dockerfile_to)
            )
            return True
        except IOError:
            logger.warning("Failed to add file {}".format(path))
            return False


def main():
    import pkg_resources
    version = pkg_resources.require("docker_microsync")[0].version
    arguments = docopt(__doc__, version=version)
    if arguments['--file-extensions']:
        input_file_extensions = arguments['--file-extensions'].split(",")
    else:
        input_file_extensions = None
    main_logger = logging.getLogger(__name__)

    handler = logging.StreamHandler(stream=sys.stdout)
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)
    timeout = float(arguments['--timeout'])
    if not timeout:
        print("Timeout is not valid, has to be 0.1 or more")
        sys.exit(1)
    sync = DockerMicrosync(arguments['<path>'], arguments['<prefix_path>'],
                           arguments['<base_image>'], input_file_extensions,
                           timeout)

    try:
        sync.start()
    except KeyboardInterrupt:
        sync.stop()
    print("Shutting down, built {} new images".format(sync.builds))


if __name__ == "__main__":
    main()
