# OEM Image Monitor

OEM image monitor is a tool to monitor the Ubuntu OEM image release status.

> This tool is for Dell oem image only at the moment

## Components

- Python utility to look up the image status from image release website

- C library to store the (Ubuntu One) credentical

## Deployment

- Clone the repoistory to local disk

- Use below command to install dependency and prepare the runtime environment

  - ./bootstrap

- Build the credentical library

  - Update your own Ubuntu One account and password in lp_auth.c

  - gcc -shared -o libuo_auth.so -fPIC lp_auth.c

## Usage

The tool is currently support running on 2 different mode

- Apply the virtual environment first before running the tool

  - source environ/bin/activate

- Running on default headless mode without browser window

  - python3 image_monitor.py

- Running on 'display' mode with browser window

  - python3 image_monitor.py -d
