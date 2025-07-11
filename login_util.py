import ctypes
import sys
import time
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options

DEFAULT_WAIT_SEC = 10

def get_ubuntu_one_identity():
    uo_identity = {
            'username': '',
            'password': '',
            }
    print('Parsing Ubuntu One Identity...')
    try:
        lib = ctypes.CDLL('./libuo_auth.so')

        lib.get_username.restype = ctypes.c_char_p
        lib.get_password.restype = ctypes.c_char_p

        uo_identity['username'] = lib.get_username().decode('utf-8')
        uo_identity['password'] = lib.get_password().decode('utf-8')
    except OSError:
        print("[Error] Missing launchpad identity library")
        raise OSError

    print('Successfully parsed user identity')
    return uo_identity


def login_util():
    # get Ubuntu One Identity
    try:
        uo_identity = get_ubuntu_one_identity()
    except OSError:
        sys.exit(-1)

    options = Options()
    #options.add_argument("--headless")

    print('Initalizing Web Engine...')
    service = Service('/snap/bin/geckodriver')
    driver = webdriver.Firefox(service=service, options=options)

    driver.get('https://oem-share.canonical.com/partners/somerville/share/releases/noble/')
    driver.switch_to.window(driver.window_handles[0])

    wait_for_page_loading()

    # input username and password
    userid = driver.find_element(By.ID, 'id_email')
    userid.send_keys(uo_identity['username'])

    pwd = driver.find_element(By.ID, 'id_password')
    pwd.send_keys(uo_identity['password'])

    login_btn = driver.find_element(By.NAME, 'continue')
    login_btn.click()

    wait_for_page_loading()

    # Persinal Data Detail confirmation
    login_btn_2 = driver.find_element(By.NAME, 'yes')
    login_btn_2.click()

    wait_for_page_loading()
    cookies = driver.get_cookies()
    

def wait_for_page_loading():
    # wait for the page loading
    print('Waiting for page loading complete...')
    time.sleep(DEFAULT_WAIT_SEC)


if __name__ == '__main__':

    login_util()
    sys.exit(0)
