# OEM Image Monitor

OEM image monitor is a tool to monitor the Ubuntu OEM image release status.

> This tool is for Dell oem image only at the moment

## Components

- Python utility to look up the image status from image release website

- C library to store the (Ubuntu One) credentical

- Bash script of command line utility

## Deployment

- Clone the repoistory to local disk

- Use below command to install dependency and prepare the runtime environment

  - ./bootstrap

- Build the credentical library

  - Update your own Ubuntu One account and password in lp_auth.c

  - gcc -shared -o libuo_auth.so -fPIC lp_auth.c

## Usage

Use command line utility with below command:

- ./scripts/image_monitor