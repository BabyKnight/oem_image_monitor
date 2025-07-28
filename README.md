# OEM Image Monitor

OEM image monitor is a tool to monitor the Ubuntu OEM image release status and download to local stroage.

> This tool is for Dell oem image only at the moment

## Components

- Python utility to look up the image status from image release website

- C library to store the (Ubuntu One) credentical

- Bash script of command line utility

- cron job to run the utility regularly

## Deployment

- Clone the repoistory to local disk

- Use below command to clean up the previous environment if it's not the 1st time to deploy (Optional)

  - ./bootstrap --clean

- Use below command to install dependency and prepare the runtime environment

  - ./bootstrap

- Build the credentical library

  - Update your own Ubuntu One account and password in lp_auth.c

  - gcc -shared -o libuo_auth.so -fPIC lp_auth.c

- Customize the settings for the utility (Optional)

  - Modify the settings in file 'config.yaml'

  > Please note: When specifying the file or log save directory, make sure you have the necessary permissions for that directory. Otherwise, please run the command/utility as root user.

- Use below command to deploy the cron (Optional)

  -  ./scripts/image_monitor --add-cron

## Usage

Use command line utility with below command:

  - ./scripts/image_monitor  or ./scripts/image_monitor --run

New download task will be temporarily saved in json file which set in config.yaml

> e.g. image_download_queue: IMAGE_DOWNLOAD_QUEUE

New released image will be downloaded to the path which set in config.yaml

> e.g. image_download_path: /tmp

Released image information will be saved at a json file which set in config.yaml

> e.g. released_image_data: RELEASED_IMAGE_DATA

## Contributing

- Environment

  - The project is developed based on Python 3.12 (earlier version are not verified), please use 3.12 or newer version to make sure it's compatible with the current code

  - Please use virtualenv for this project

- Coding style

  - Before submit PR, please make sure it passed flake8