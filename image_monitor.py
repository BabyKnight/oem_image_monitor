import ctypes
import sys
import time
from datetime import date
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options


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


class Monitor:
		default_wait_sec = 10
		image_dict = {}
		image_category = {}
		image_released_today = {}
		display = True

		def __init__(self, display=False):

				self.display = display

				options = Options()
				if not display:
						options.add_argument("--headless")

				print('Initalizing Web Engine...')
				service = Service('/snap/bin/geckodriver')
				self.driver = webdriver.Firefox(service=service, options=options)

		def __wait_for_page_loading(self):
				# wait for the page loading
				print('Waiting for page loading complete...')
				time.sleep(self.default_wait_sec)
			
		def lookup_for_image(self):
				# get Ubuntu One Identity
				try:
						uo_identity = get_ubuntu_one_identity()
				except OSError:
						self.driver.quit()
						sys.exit(-1)

				self.driver.get('https://oem-share.canonical.com/partners/somerville/share/releases/noble/')
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

				# find all image category
				self.driver.find_elements(By.CSS_SELECTOR, 'tr')[3:-1]

				for i in self.driver.find_elements(By.CSS_SELECTOR, 'tr')[3:-1]:
						category = i.find_element(By.CSS_SELECTOR,'a').text.rstrip('/')
						# ignore the folder 'sideload'
						if category == 'sideload':
								continue
						self.image_category[category] = i.find_element(By.CSS_SELECTOR,'a').get_property('href')

				# fetch all the image category, e.g. 24.04a, 24.04a-next, 24.04b, 24.04b-proposed
				print('Image Category Found:')
				for key in self.image_category.keys():
						print('\t|-' + key)

				for img_cat, img_cat_url in self.image_category.items():

						self.image_dict[img_cat] = []
						print(img_cat_url.rstrip('/').split('/')[-1])

						self.driver.get(img_cat_url)
						time.sleep(5)

						image_dir_link_list = []
						# start from the 3rd elements since 0~2 are title and link for parent directory
						elem_image_dir = self.driver.find_elements(By.CSS_SELECTOR, 'tr')[3:-1]
						for i in elem_image_dir:
								link = i.find_element(By.CLASS_NAME, 'indexcolname').find_element(By.CSS_SELECTOR, 'a').get_property('href')
								image_dir_link_list.append(link)

						for i in image_dir_link_list:
								dir_name = i.rstrip('/').split('/')[-1]
								print("\t |- " + dir_name)

								# Check if iso image is released
								self.driver.get(i)
								time.sleep(5)
								for file in self.driver.find_elements(By.CSS_SELECTOR, 'tr')[3:-1]:
										filename, last_modified = file.text.split()[:2]
										if '.iso' in filename:
												print("\t\t|-" + filename + " [" + last_modified + "]")
												self.image_dict[img_cat].append({'dir_name':dir_name, 'file_name':filename, 'last_modified': last_modified})
												if date.today() == date.fromisoformat(last_modified):
														self.image_released_today[filename] = i + filename

				self.driver.quit()

		def generate_report(self):
				print("Generating report...")

				with open("image_released_today.txt", "w") as file:
						if not self.image_released_today:
								print("No image released today!")
						else:
								for img, link in self.image_released_today.items():
										file.write("Image: " + img + "Download link: "+ link  +"\n")


if __name__ == '__main__':

		# accept a command line argument, program will running on Slience mode without open browser window by default, display browser with argu '-d'
		display_mode = False
		if len(sys.argv) > 1:
				if sys.argv[1] == '-d':
						display_mode = True

		image_monitor = Monitor(display_mode)
		image_monitor.lookup_for_image()
		image_monitor.generate_report()
		sys.exit(0)
