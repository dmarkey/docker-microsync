from setuptools import setup

with open('requirements.txt') as f:
    required = f.read().splitlines()

setup(
    use_scm_version=True,
    setup_requires=['setuptools_scm'],
    name='docker_microsync',
    packages=['docker_microsync'],
    license='MIT',
    install_requires=required,
    entry_points={
        'console_scripts': [
            'docker-microsync = docker_microsync:main']
    }

)
