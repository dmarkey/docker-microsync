"""Docker Microsync

Usage:
  docker_microsync.py <path> <prefix_path> <base_image>  [--file-extensions=<csv_list>]
  docker_microsync.py -h | --help | --version
"""
import sys

import io
import tarfile
from docopt import docopt
from queue import SimpleQueue, Empty
from watchdog.events import FileSystemEventHandler, FileMovedEvent, \
    FileCreatedEvent, FileModifiedEvent
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
                 timeout=2):
        self.path = path
        self.base_image = base_image
        self.file_extensions = tuple(file_extensions)

        self.timeout = timeout
        self.observer = Observer()
        self.outbound_queue = SimpleQueue()
        self.docker_client = docker.from_env()
        self.prefix_path = prefix_path
        self.stopping = False
        event_handler = QueueFileSystemEventHandler(
            outbound_queue=self.outbound_queue)
        self.observer.schedule(event_handler, ".", recursive=True)

    def start(self):
        logger.info("Starting to watch for changed files.")
        self.observer.start()
        while True:
            dockerfile = ["from {}".format(self.base_image)]
            tarbuffer = io.BytesIO()
            tf = tarfile.TarFile(fileobj=tarbuffer, mode='w')
            files_added = False
            while True:
                if self.stopping:
                    return

                try:
                    event = self.outbound_queue.get(timeout=self.timeout)
                    if isinstance(event, FileMovedEvent):
                        if self._add_file(tf, dockerfile, event.dest_path):
                            files_added = True
                    if isinstance(event, FileCreatedEvent):
                        if self._add_file(tf, dockerfile, event.src_path):
                            files_added = True
                    if isinstance(event, FileModifiedEvent):
                        if self._add_file(tf, dockerfile, event.src_path):
                            files_added = True

                except Empty:
                    if files_added:
                        _tar_add_bytes(tf, "Dockerfile", "\n".join(dockerfile))
                        tarbuffer.seek(0)
                        self.docker_client.images.build(
                            fileobj=tarbuffer,
                            custom_context=True,
                            tag=self.base_image)
                        break

    def stop(self):
        self.observer.stop()

    def _add_file(self, tf, dockerfile, path):
        logger.info("Adding file {}".format(path))
        if self.file_extensions and not path.endswith(self.file_extensions):
            return False
        try:
            f = open(path, "rb")
            _tar_add_bytes(tf, path, f.read())
            dockerfile.append(
                "copy '{}' 'P{}/{}'\n".format(path, self.prefix_path,
                                              path))
            return True
        except IOError:
            logger.warning("Failed to add file {}".format(path))
            return False


if __name__ == "__main__":
    arguments = docopt(__doc__, version='0.1')
    if arguments['--file-extensions']:
        file_extensions = arguments['--file-extensions'].split(",")
    else:
        file_extensions = None
    logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
    sync = DockerMicrosync(arguments['<path>'], arguments['<prefix_path>'],
                           arguments['<base_image>'], file_extensions)

    try:
        sync.start()
    except KeyboardInterrupt:
        sync.stop()



