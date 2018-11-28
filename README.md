# docker-microsync
A really simple way to do rapid development with docker/kubernetes.

# Quickstart
Prerequisites:
1. A kubernetes cluster (tested on minikube)
2. Freshpod deployed
3. A python3 interpreter locally.

## Installation
pip install docker-microsync

## Usage

Lets say you have a development image tagged myimage:latest current deployed and is up to date, this image is running a project thats built from the current directory and this directory is mapped to /opt/src, you would invoke docker-microsync like this:

`docker-microsync . /opt/src  myimage:latest`

And changes in the current directory will be copied to /opt/src in the docker image.

## Advanced usage

You can tweak the timeout by using the `--timeout` command line option and you can specify a list of file extensions to pay attention to by supplying a list comma separated to the `--file-extensions` flag.


# Demo App

Using the "demo" app that is supplied.

```
➜  demo eval $(minikube docker-env)
➜  demo docker build . -t docker-microsync:latest

Sending build context to Docker daemon  4.608kB
Step 1/2 : from nginx:1.15.7
 ---> 568c4670fa80
Step 2/2 : COPY message.txt /usr/share/nginx/html
 ---> 1351305b2ee4
Successfully built 1351305b2ee4
Successfully tagged docker-microsync:latest
➜  demo kubectl apply -f yaml/*        
deployment.apps/nginx-deployment created
➜  demo kubectl expose deployment nginx-deployment --type=LoadBalancer --name=my-service
service/my-service exposed
➜  demo kubectl get svc
NAME         TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)        AGE
kubernetes   ClusterIP      10.96.0.1       <none>        443/TCP        3m
my-service   LoadBalancer   10.100.46.146   <pending>     80:31010/TCP   39s
➜  demo minikube ip
192.168.99.100
➜  demo kubectl get svc
NAME         TYPE           CLUSTER-IP      EXTERNAL-IP   PORT(S)        AGE
kubernetes   ClusterIP      10.96.0.1       <none>        443/TCP        3m
my-service   LoadBalancer   10.100.46.146   <pending>     80:31010/TCP   39s
➜  demo curl 192.168.99.100:31010/message.txt
My message   # this is the old message 
➜  demo pip install docker-microsync # install docker-microsync
➜  demo docker-microsync . /usr/share/nginx/html docker-microsync:latest

Starting to watch for changed files - 0.5 second timeout.

<switch terminal>
➜  demo echo "My lovely new message" > message.txt 
< 5 second wait>

➜  demo curl 192.168.99.100:31010/message.txt                           
My lovely new message




```

# What does it do?
This tool runs on your local development environment and watches the filesystem for changes.
After a timeout period, (default 0.5 seconds) It proceeds to build a docker image, which is based on the latest image for your app.
This is a complementary to "freshpod" (https://github.com/GoogleCloudPlatform/freshpod) which will re-deploy running pods that are using the image.

# Why?
I seen the need for a tool that is uncomplicated. Similar tools require creating VPNs etc. which seems complicated. This requires no special networking etc and freshpod comes out of the box with tools like Minikube.

This tool is known to work on Linux and OSX, in theory it can work on windows but this is untested.

# How does it work?
It's quite simple. It uses the excellent watchdog library to watch for filesystem changes in a platform independent way. 
It then keeps an in-memory docker context and adds any changed files to that context. After a specific period of timeout it sends the context along with a Dockerfile and this adds the required layers to the current running image and tags it accordingly.

Freshpod then redeploys any running pods using the image as it sees that a new image has been tagged.

# How long does it take to deploy my new code?

It depends how long your app takes to initialise. The new image will be built in 1-3 seconds and it usually takes another 5 seconds for kubernetes to redeploy an application.

# Limitations

It runs in memory so big files that are changing will be slow and memory hungry. Moving files doesnt delete the old file (PRs welcome)

File attributes(like executable) arent copied.
