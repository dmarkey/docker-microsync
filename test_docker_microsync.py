import sys
import time

import logging
import os

import io
import tarfile
from shutil import rmtree

from unittest.mock import MagicMock, patch
from threading import Thread
from watchdog.events import FileMovedEvent, FileCreatedEvent, FileModifiedEvent


def test_tar_add_bytes():
    import docker_microsync
    tarbuffer = io.BytesIO()
    tf = tarfile.TarFile(fileobj=tarbuffer, mode='w')
    docker_microsync._tar_add_bytes(tf, "test_docker_microsync.py", b'123456')
    docker_microsync._tar_add_bytes(tf, "test_docker_microsync2.py", '123456')
    info = tf.getmember("test_docker_microsync.py")
    assert info.size == 6
    info = tf.getmember("test_docker_microsync2.py")
    assert info.size == 6


@patch("docker_microsync.docker")
def test_docker_microsync(*args):
    import docker_microsync
    docker_mock = args[0]
    build = MagicMock(return_value=("base/base:latest", None))
    docker_mock.from_env().images.build = build

    rmtree("test_dir", ignore_errors=True)
    os.mkdir("test_dir")
    main_logger = logging.getLogger(docker_microsync.__name__)

    handler = logging.StreamHandler(stream=sys.stdout)
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)
    microsync = docker_microsync.DockerMicrosync("test_dir", "/prefix",
                                                 "base/base:latest",
                                                 timeout=0.5)
    microsync.observer = MagicMock()

    t = Thread(target=microsync.start)
    t.start()
    with open("test_dir/test1", "w") as f:
        f.write("lala")
    with open("test_dir/test2", "w") as f:
        f.write("bobo")
    with open("test_dir/test3", "w") as f:
        f.write("ahah")
    with open("test_dir/test4", "w") as f:
        f.write("wowo")
    microsync.outbound_queue.put(FileMovedEvent(src_path="none",
                                                dest_path="test_dir/test1"))
    microsync.outbound_queue.put(FileCreatedEvent(src_path="test_dir/test2"))
    microsync.outbound_queue.put(FileModifiedEvent(src_path="test_dir/test3"))
    time.sleep(1)
    microsync.outbound_queue.put(FileModifiedEvent(src_path="test_dir/test4"))
    microsync.outbound_queue.put(FileModifiedEvent(
        src_path="test_dir/test_nofile"))
    time.sleep(1)
    microsync.stop()
    (args, kwargs) = build.call_args_list[0]
    assert kwargs['custom_context'] == True
    assert kwargs['tag'] == "base/base:latest"
    tf = tarfile.TarFile(fileobj=kwargs['fileobj'], mode='r')
    assert tf.extractfile(tf.getmember("test1")).read() == b"lala"
    assert tf.extractfile(tf.getmember("test2")).read() == b"bobo"
    assert tf.extractfile(tf.getmember("test3")).read() == b"ahah"
    assert tf.extractfile(tf.getmember(
        "Dockerfile")).read() == b"from base/base:latest\ncopy 'test1'" \
                                 b" '/prefix/test1'\n\ncopy 'test2'" \
                                 b" '/prefix/test2'\n\ncopy 'test3'" \
                                 b" '/prefix/test3'\n"

    (args, kwargs) = build.call_args_list[1]
    assert kwargs['custom_context'] == True
    assert kwargs['tag'] == "base/base:latest"
    tf = tarfile.TarFile(fileobj=kwargs['fileobj'], mode='r')
    assert tf.extractfile(tf.getmember(
        "Dockerfile")).read() == b"from base/base:latest\ncopy" \
                                 b" 'test4' '/prefix/test4'\n"

    assert tf.extractfile(tf.getmember("test4")).read() == b"wowo"
    t.join()


@patch("docker_microsync.docker")
def test_docker_microsync_paths(*args):
    import docker_microsync
    docker_mock = args[0]
    build = MagicMock(return_value=("base/base:latest", None))
    docker_mock.from_env().images.build = build

    rmtree("test_dir", ignore_errors=True)
    os.mkdir("test_dir")
    main_logger = logging.getLogger(docker_microsync.__name__)

    handler = logging.StreamHandler(stream=sys.stdout)
    main_logger.addHandler(handler)
    main_logger.setLevel(logging.INFO)
    microsync = docker_microsync.DockerMicrosync("test_dir", "/prefix",
                                                 "base/base:latest",
                                                 timeout=0.5,
                                                 file_extensions=[".py",
                                                                  ".txt"])
    microsync.observer = MagicMock()

    t = Thread(target=microsync.start)
    t.start()
    with open("test_dir/test1.py", "w") as f:
        f.write("lala")
    with open("test_dir/test2", "w") as f:
        f.write("bobo")
    with open("test_dir/test3.txt", "w") as f:
        f.write("ahah")

    microsync.outbound_queue.put(FileMovedEvent(src_path="none",
                                                dest_path="test_dir/test1.py"))
    microsync.outbound_queue.put(FileCreatedEvent(src_path="test_dir/test2"))
    microsync.outbound_queue.put(FileModifiedEvent(src_path="test_dir/test3.txt"))
    time.sleep(1)

    microsync.stop()
    (args, kwargs) = build.call_args_list[0]
    assert kwargs['custom_context'] == True
    assert kwargs['tag'] == "base/base:latest"
    tf = tarfile.TarFile(fileobj=kwargs['fileobj'], mode='r')
    assert tf.extractfile(tf.getmember("test1.py")).read() == b"lala"
    assert tf.extractfile(tf.getmember("test3.txt")).read() == b"ahah"
    assert tf.extractfile(tf.getmember(
        "Dockerfile")).read() == b"from base/base:latest\ncopy 'test1.py'" \
                                 b" '/prefix/test1.py'\n\ncopy 'test3.txt'" \
                                 b" '/prefix/test3.txt'\n"
    t.join()
