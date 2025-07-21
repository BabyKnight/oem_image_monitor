import ctypes
import json
import logging
import os
import requests
import sys
import time
from bs4 import BeautifulSoup
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options

DATA_PATH = 'data'
LOG_PATH = 'logs'
SAVED_COOKIES = os.path.join(DATA_PATH,'SESSION_DATA')
RELEASED_IMAGE_DATA = os.path.join(DATA_PATH,'RELEASED_IMAGE_DATA')
IMAGE_DOWNLOAD_QUEUE = os.path.join(DATA_PATH,'IMAGE_DOWNLOAD_QUEUE')
BASE_URL = 'https://oem-share.canonical.com/partners/somerville/share/releases/noble/'


if not os.path.exists(LOG_PATH):
    os.makedirs(LOG_PATH)

logging.basicConfig(
    filename=LOG_PATH + '/image_tracker.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


def get_ubuntu_one_identity():
    """
    Method to get Ubuntu One identity from the library
    """
    uo_identity = {
            'username': '',
            'password': '',
            }
    logging.info('Parsing Ubuntu One Identity')
    try:
        lib = ctypes.CDLL('./libuo_auth.so')

        lib.get_username.restype = ctypes.c_char_p
        lib.get_password.restype = ctypes.c_char_p

        uo_identity['username'] = lib.get_username().decode('utf-8')
        uo_identity['password'] = lib.get_password().decode('utf-8')
    except OSError:
        logging.error('Launchpad identity library not found')
        raise OSError

    logging.info('Parsing user identity completed')
    return uo_identity


class ImageMonitor:

    default_wait_sec = 10
    driver = None
    session = None
    img_release_history = {}
    img_download_queue = []

    def __wait_for_page_loading(self):
        # wait for the page loading
        logging.info('Waiting for page load complete')
        time.sleep(self.default_wait_sec)

    def update_cookie(self):
        """
        Use user name and password to login the website, then get and save the session cookies data into local file
        Note: this method will auto close the browser once get the cookies
        """
        self.login()
        cookies = self.driver.get_cookies()
        self.driver.quit()

        with open(SAVED_COOKIES, 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False)
            logging.info('Cookies in session updated and saved')

    def update_session(self):
        """
        Update the user session with saved cookie data or from webengine (driver)
        """
        # check if saved cookies available
        if not os.path.exists(SAVED_COOKIES):
            logging.info('Saved cookie data not found')
            self.update_cookie()
        else:
            logging.info('Saved cookie data found')

        with open(SAVED_COOKIES, 'r', encoding='utf-8') as f:
            content = f.read()
        try:
            cookies = json.loads(content)
        except json.JSONDecodeError as e:
            logging.warning('Json decode error in the saved cookie data', e)
            logging.info('Starting re-generate the user session cookie data')
            self.update_cookie()

        # initial/recover the session
        logging.info('Initializing the session with saved cookies data')
        self.session = requests.Session()
        for cookie in cookies:
            self.session.cookies.set(cookie['name'], cookie['value'])


    def login(self):
        """
        Method to login
        Note: Need to manually call the methon to close the browser - self.driver.quit()
        """
        # get Ubuntu One Identity
        logging.info('Starting login with given identity')
        try:
            uo_identity = get_ubuntu_one_identity()
        except OSError:
            sys.exit(-1)

        options = Options()
        # default to use headless mode without display
        options.add_argument('--headless')

        logging.info('Initalizing the Web Engine')
        service = Service('/snap/bin/geckodriver')
        self.driver = webdriver.Firefox(service=service, options=options)

        self.driver.get(BASE_URL)
        self.driver.switch_to.window(self.driver.window_handles[0])

        self.__wait_for_page_loading()

        # input username and password
        userid = self.driver.find_element(By.ID, 'id_email')
        userid.send_keys(uo_identity['username'])

        pwd = self.driver.find_element(By.ID, 'id_password')
        pwd.send_keys(uo_identity['password'])

        login_btn = self.driver.find_element(By.NAME, 'continue')
        login_btn.click()

        self.__wait_for_page_loading()

        # Persinal Data Detail confirmation
        login_btn_2 = self.driver.find_element(By.NAME, 'yes')
        login_btn_2.click()

        self.__wait_for_page_loading()
        logging.info('User authenticated')

    def check_for_updates(self):
        """
        Method to check for the image release status
        """
        logging.info('Starting the task to check for image updates')
        self.get_img_release_hist()

        self.update_session()

        response = self.session.get(BASE_URL)

        # check if session expire
        while self.is_session_expire(response):
            self.update_cookie()
            self.update_session()
            response = self.session.get(BASE_URL)

        img_cate_dict = self.parse_category(response.text)
        for cate, v in img_cate_dict.items():
            logging.info('[' + cate + ']')
            self.img_release_history[cate] = self.parse_image_by_category(cate, v['link'])

        self.save_img_release_hist()
        self.save_img_download_queue()
        self.download_image_in_queue()
        logging.info('The task to check for image updates complete')

    def is_session_expire(self, res):
        if res.url == 'https://oem-share.canonical.com/openid/+login' or 'OpenID Authentication Required' in res.text:
            logging.info('Session expire.')
            return True
        return False

    def parse_category(self, res):
        """
        parse the imaghe category and link
        return a dict with <image_category>:<link>
        """
        img_cate_dict = {}
        bs = BeautifulSoup(res, 'html.parser')
        rows = bs.find_all('tr', class_=['odd', 'even'])
        # bypass the 1st row since it's the link back to Parent Directory
        for row in rows[1:]:
            for a in row.find_all('a', href=True):
                img_cate = a.get_text(strip=True).rstrip('/')
                # skip when the folder name is 'sideload'
                if img_cate != 'sideload':
                    img_cate_dict[img_cate] = {
                            'link': BASE_URL + a['href']
                            }

        return img_cate_dict
        
    def parse_image_by_category(self, cate, url):
        """
        method to parse image by category
        return a list of image info by a individual category
        """
        image_info_list = []
        img_dict = {}
        response = self.session.get(url)
        bs = BeautifulSoup(response.text, 'html.parser')

        rows = bs.find_all('tr', class_=['odd', 'even'])
        # bypass the 1st row since it's the link back to Parent Directory
        for row in rows[1:]:
            for a in row.find_all('a', href=True):
                img_dir = a.get_text(strip=True).rstrip('/')
                img_dict[img_dir] = {
                            'link': url + a['href']
                        }
                logging.info('  |- [' + img_dir +  ']')
                response = self.session.get(url + a['href'])
                bs = BeautifulSoup(response.text, 'html.parser')

                rows = bs.find_all('tr', class_=['odd', 'even'])
                # bypass the 1st row since it's the link back to Parent Directory
                for row in rows[1:]:
                    for a in row.find_all('a', href=True):
                        logging.info('    |- ' + a.get_text(strip=True))

                        if '.iso' in a.get_text(strip=True):
                            image_filename = a.get_text(strip=True)
                            image_link = response.url + image_filename
                            logging.info('      |-' + image_link)
                            image_info_list.append({
                                'image_filename': image_filename,
                                'image_link': image_link,
                                })
                            if cate in self.img_release_history and not any(d.get('image_filename') == image_filename for d in self.img_release_history[cate]):
                                logging.info('        |-[' + image_filename + '] is not downloaded yet,  adding to the queue')
                                self.img_download_queue.append({
                                    'image_filename': image_filename,
                                    'image_link': image_link,
                                    })

                        if '.sha256sum' in a.get_text(strip=True):
                            checksum_filename = a.get_text(strip=True)
                        if '.sbom' in a.get_text(strip=True):
                            sbom_filename = a.get_text(strip=True)
                        
        return image_info_list

    def get_img_release_hist(self):
        """
        Method to read the image release history
        Return/initial a json data which cal be used for checking if image has been recorded & downloaded
        """
        # if the file for history data is not exist, leave it for saving method to create the file
        if os.path.exists(RELEASED_IMAGE_DATA):
            with open(RELEASED_IMAGE_DATA, 'r', encoding='utf-8') as f:
                self.img_release_history = json.load(f)
                logging.info('Image historical data found in local')

    def save_img_release_hist(self):
        """
        Method to set/save the released image data to local
        """
        logging.info('Saving the image historical data to local')
        # create a new file if not exists
        with open(RELEASED_IMAGE_DATA, 'w', encoding='utf-8') as f:
            json.dump(self.img_release_history, f, indent=4, ensure_ascii=False)

    def save_img_download_queue(self):
        # create a new file if not exists, overwrite if file exists
        logging.info('Refreshing the image download queue')
        logging.info('[' + str(len(self.img_download_queue)) + '] images in the download queue')
        with open(IMAGE_DOWNLOAD_QUEUE, 'w', encoding='utf-8') as f:
            json.dump(self.img_download_queue, f, indent=4, ensure_ascii=False)

    def download_image_in_queue(self):
        """
        Method to download all the image set in the download queue
        """
        for image in self.img_download_queue:
            with self.session.get(image['image_link'], stream=True) as res:
                logging.info('Starting to download the new image [' + image['image_filename'] + ']')
                res.raise_for_status()
                with open(os.path.join(DATA_PATH,image['image_filename']), 'wb') as f:
                    for chunk in res.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
            logging.info('Image [' + image['image_filename'] + '] download complete')
            # remove from the download queue in case any exception during next image download
            self.img_download_queue.remove(image)
            self.save_img_download_queue()


if __name__ == '__main__':
    image_tracker = ImageMonitor()
    image_tracker.check_for_updates()
    sys.exit(0)