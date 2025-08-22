import ctypes
import json
import logging
import os
import requests
import sys
import time
import yaml
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options


CONFIG = {'DEFAULT_SETTING_FILE': 'config.yaml'}


def init_utility():
    """
    Define a unified method to include all necessary preliminary steps
    """
    load_config()
    init_logging()


def load_config():
    """
    Loading the config file for the utility initialize
    """
    # global CONFIG
    if os.path.exists(CONFIG['DEFAULT_SETTING_FILE']):
        with open(CONFIG['DEFAULT_SETTING_FILE'], 'r', encoding='utf-8') as f:
            conf = yaml.safe_load(f)

            CONFIG['DATA_PATH'] = conf['file_and_path']['data_path']
            CONFIG['SAVED_COOKIES'] = os.path.join(CONFIG['DATA_PATH'], conf['file_and_path']['saved_cookies'])
            CONFIG['RELEASED_IMAGE_DATA'] = os.path.join(CONFIG['DATA_PATH'], conf['file_and_path']['released_image_data'])
            CONFIG['IMAGE_DOWNLOAD_QUEUE'] = os.path.join(CONFIG['DATA_PATH'], conf['file_and_path']['image_download_queue'])
            CONFIG['BASE_URL'] = conf['url']['base_url']
            CONFIG['LOG_PATH'] = conf['logging']['log_path']
            CONFIG['LOG_LEVEL'] = conf['logging']['level']
            CONFIG['LOG_FILE'] = conf['logging']['file']
            CONFIG['KEEP_SBOM'] = conf['file_and_path']['keep_sbom']
            CONFIG['IMAGE_DOWNLOAD_PATH'] = conf['file_and_path']['image_download_path']
            CONFIG['EXTENSION_ENABLED'] = conf['extension']['enabled']
            CONFIG['EXTENSION_URL'] = conf['extension']['url']
    else:
        # the config file should be stored at the same directory as this python file
        # please create/modify the config file or checkout the default config
        # this should not happen but in case the config file been deleted
        logging.error('Config file not found, please create the config file or checkout the default config')
        sys.exit(0)


def init_logging():
    """
    Initialize the logging
    """
    log_path = CONFIG['LOG_PATH']
    if not os.path.exists(log_path):
        os.makedirs(log_path)

    log_level = getattr(logging, CONFIG['LOG_LEVEL'].upper(), logging.INFO)

    logging.basicConfig(
        filename=os.path.join(log_path, CONFIG['LOG_FILE']),
        level=log_level,
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


def pasre_sbom(sbom_file, pkg_name=None):
    """
    Method to parse sbom from file
        - if the package name is given, return the package version
        - if the package name is not given, return all the packages version info
    """
    try:
        with open(sbom_file, 'r', encoding='utf-8') as f:
            sbom_data = yaml.safe_load(f)

        if pkg_name:
            for package_name, details in sbom_data.items():
                if pkg_name in package_name:
                    pkg_version = details['version']
                    return pkg_version

        else:
            pkg_ver_dict = {}

            for package_name, details in sbom_data.items():
                pkg_ver_dict[package_name] = details['version']
            return pkg_ver_dict

    except FileNotFoundError:
        logging.error('no sbom file found')
    except yaml.YAMLError as e:
        logging.error('Parsing sbom error: %s', e)
    except Exception as e:
        logging.error('Unknown error: %s', e)


def get_kernel_ver_from_sbom(sbom_file):
    """
    Method to get kernel version from a given sbom file
     - Check the package name which start with 'linux-oem'
        -e.g. linux-oem-6.11
    """
    kern_ver = pasre_sbom(sbom_file, 'linux-oem')
    return kern_ver


def get_iso_sha256sum_from_file(checksum_file):
    """
    Method to get the iso sha256 checksum from the sha256sum file
    """
    if os.path.exists(checksum_file):
        with open(checksum_file, 'r', encoding='utf-8') as f:
            for line in f:
                if '.iso' in line.strip():
                    iso_sha256sum = line.strip().split(' ')[0]
                    return iso_sha256sum


def get_image_version_from_filename(img_filename):
    """
    Method to get the image version from a given image filename
    """
    if img_filename and img_filename[-4:] == '.iso':
        img_ver = image_filename.split('.iso')[0].split('-')[-1]
    else:
        img_ver = None
    return img_ver


def get_image_category(cate_folder_name):
    """
    Method to get the image category from the folder name
    valid category:
        - edge
        - next
        - proposed
        - production
    """
    valid_cat = ['edge', 'next', 'proposed', 'production']
    posible_cat = cate_folder_name.split('-')[-1]
    if posible_cat in valid_cat:
        return posible_cat
    else:
        return 'production'


def add_image_info(img_name, kern_ver, date_str, path, size, checksum, img_cat, img_ver=None):
    """
    Method to update image info (send data to server)
    """
    url = CONFIG['EXTENSION_URL']
    release_date = datetime.strptime(date_str, "%Y-%m-%d %H:%M")

    data = {
        "name": img_name,
        "cat": img_cat,
        "img_ver": img_ver,
        "kern_ver": kern_ver,
        "date": release_date,
        "path": path,
        "size":size,
        "checksum": checksum,
    }

    res = requests.post(url,  data=data)
    if res.text == 0:
        logging.error('Adding image info success')
    else:
        logging.error('Adding image info failed with return code %s', res.text)


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

        with open(CONFIG['SAVED_COOKIES'], 'w', encoding='utf-8') as f:
            json.dump(cookies, f, ensure_ascii=False)
            logging.info('Cookies in session updated and saved')

    def update_session(self):
        """
        Update the user session with saved cookie data or from webengine (driver)
        """
        # check if saved cookies available
        if not os.path.exists(CONFIG['SAVED_COOKIES']):
            logging.info('Saved cookie data not found')
            self.update_cookie()
        else:
            logging.info('Saved cookie data found')

        with open(CONFIG['SAVED_COOKIES'], 'r', encoding='utf-8') as f:
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

        self.driver.get(CONFIG['BASE_URL'])
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

        response = self.session.get(CONFIG['BASE_URL'])

        # check if session expire
        while self.is_session_expire(response):
            self.update_cookie()
            self.update_session()
            response = self.session.get(CONFIG['BASE_URL'])

        img_cate_dict = self.parse_category(response.text)
        for cate, v in img_cate_dict.items():
            logging.info('Image category [' + cate + '] found')
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
                            'link': CONFIG['BASE_URL'] + a['href']
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
                # print the image folder name
                logging.info('Image directory [' + img_dir + '] found')
                response = self.session.get(url + a['href'])
                bs = BeautifulSoup(response.text, 'html.parser')

                image_info_dict = {
                        'image_cate': cate,
                        'image_version': None,
                        'kernel_version': 'Unknown',
                        }
                rows_for_a_img = bs.find_all('tr', class_=['odd', 'even'])
                # bypass the 1st row since it's the link back to Parent Directory

                new_released = False
                for row_in_img_dir in rows_for_a_img[1:]:

                    kernel_version = ""
                    for a in row_in_img_dir.find_all('a', href=True):

                        if '.iso' in a.get_text(strip=True):
                            image_filename = a.get_text(strip=True)
                            image_link = response.url + image_filename
                            logging.info('Image iso file ' + image_filename + ' found')
                            image_info_dict['image_filename'] = image_filename
                            image_info_dict['image_link'] = image_link

                            if cate not in self.img_release_history or (cate in self.img_release_history and not any(d.get('image_filename') == image_filename for d in self.img_release_history[cate])):
                                logging.info('[' + image_filename + '] is not downloaded yet,  adding to the queue')
                                self.img_download_queue.append({
                                    'image_filename': image_filename,
                                    'image_link': image_link,
                                    })
                                new_released = True

                            last_modified = row_in_img_dir.find('td', class_='indexcollastmod').get_text(strip=True)
                            size = row_in_img_dir.find('td', class_='indexcolsize').get_text(strip=True)

                            logging.info('- Last Modified at: ' + last_modified)
                            logging.info('- Image size is: ' + size)

                            image_info_dict['last_modified'] = last_modified
                            image_info_dict['size'] = size

                        if '.sha256sum' in a.get_text(strip=True):
                            checksum_filename = a.get_text(strip=True)
                            sha256sum_link = response.url + checksum_filename
                            sha256sum_temp = os.path.join(CONFIG['DATA_PATH'], checksum_filename)

                            if self.download_file(sha256sum_link, sha256sum_temp):
                                sha256sum = get_iso_sha256sum_from_file(sha256sum_temp)
                                image_info_dict['sha256sum'] = sha256sum
                                os.remove(sha256sum_temp)
                                logging.info('- sha256sum: ' + sha256sum)

                        if '.sbom' in a.get_text(strip=True):
                            sbom_filename = a.get_text(strip=True)
                            sbom_link = response.url + sbom_filename
                            sbom_temp = os.path.join(CONFIG['DATA_PATH'], sbom_filename)

                            if self.download_file(sbom_link, sbom_temp):
                                kernel_version = get_kernel_ver_from_sbom(sbom_temp)
                                image_info_dict['kernel_version'] = kernel_version
                                if not int(CONFIG['KEEP_SBOM']) == 1:
                                    os.remove(sbom_temp)
                                logging.info('- Kernel version: ' + kernel_version)

                if new_released and CONFIG['EXTENSION_ENABLED']:
                    add_image_info(image_filename, kernel_version, last_modified, '/tmp', size.rstrip('G'), sha256sum, get_image_category(cate), '')

                image_info_list.append(image_info_dict)

        return image_info_list

    def get_img_release_hist(self):
        """
        Method to read the image release history
        Return/initial a json data which cal be used for checking if image has been recorded & downloaded
        """
        # if the file for history data is not exist, leave it for saving method to create the file
        if os.path.exists(CONFIG['RELEASED_IMAGE_DATA']):
            with open(CONFIG['RELEASED_IMAGE_DATA'], 'r', encoding='utf-8') as f:
                self.img_release_history = json.load(f)
                logging.info('Image historical data found in local')

    def save_img_release_hist(self):
        """
        Method to set/save the released image data to local
        """
        logging.info('Saving the image historical data to local')
        # create a new file if not exists
        with open(CONFIG['RELEASED_IMAGE_DATA'], 'w', encoding='utf-8') as f:
            json.dump(self.img_release_history, f, indent=4, ensure_ascii=False)

    def save_img_download_queue(self):
        # create a new file if not exists, overwrite if file exists
        logging.info('Refreshing the image download queue')
        logging.info('[' + str(len(self.img_download_queue)) + '] images in the download queue')
        with open(CONFIG['IMAGE_DOWNLOAD_QUEUE'], 'w', encoding='utf-8') as f:
            json.dump(self.img_download_queue, f, indent=4, ensure_ascii=False)

    def download_image_in_queue(self):
        """
        Method to download all the image set in the download queue
        """
        for image in self.img_download_queue:
            with self.session.get(image['image_link'], stream=True) as res:
                logging.info('Starting to download the new image [' + image['image_filename'] + ']')
                res.raise_for_status()
                with open(os.path.join(CONFIG['IMAGE_DOWNLOAD_PATH'], image['image_filename']), 'wb') as f:
                    for chunk in res.iter_content(chunk_size=1024*1024):
                        if chunk:
                            f.write(chunk)
            logging.info('Image [' + image['image_filename'] + '] download complete')
            # remove from the download queue in case any exception during next image download
            self.img_download_queue.remove(image)
            self.save_img_download_queue()

    def download_file(self, url, target_file):
        """
        Method to download the small file to local
        """
        try:
            response = self.session.get(url)
            response.raise_for_status()
            with open(target_file, 'wb') as f:
                f.write(response.content)

            return True
        except Exception as e:
            logging.error('File download fail with exception: %s', e)
            return False


if __name__ == '__main__':
    init_utility()
    image_tracker = ImageMonitor()
    image_tracker.check_for_updates()
    sys.exit(0)
