import os
import kivy
import time
import json
import sys

from kivy.app import App
from kivy.uix.gridlayout import GridLayout
from kivy.uix.dropdown import DropDown
from kivy.properties import ObjectProperty
from kivy.uix.screenmanager import ScreenManager, Screen, NoTransition
from kivy.uix.settings import SettingOptions, SettingSpacer, SettingsWithSidebar
from kivy.uix.scrollview import ScrollView
from kivy.uix.popup import Popup
from kivy.uix.widget import Widget
from kivy.uix.button import Button
from kivy.graphics.texture import Texture
from kivy.uix.image import Image
from kivy.uix.togglebutton import ToggleButton
from kivy.metrics import dp
from kivy.logger import Logger
from kivy.clock import mainthread
from kivy.uix.videoplayer import VideoPlayer
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.boxlayout import BoxLayout

from picamera.array import PiRGBArray
from picamera import PiCamera
import cv2
import numpy as np
import threading
from functools import partial
import glob
import imutils


photo_path = './photos'
timelapse_path = photo_path + '/timelapse'
panaroma_path = photo_path + '/panaroma'
if not os.path.exists(photo_path):
	os.mkdir(photo_path)
if not os.path.exists(timelapse_path):
	os.mkdir(timelapse_path)
if not os.path.exists(panaroma_path):
	os.mkdir(panaroma_path)
	
image_effects = []
for effect in PiCamera.IMAGE_EFFECTS:
	image_effects.append(effect)
image_effects.sort(reverse=True)
for i in range (9):
	image_effects.append("effects" + str(i))

fourcc =  cv2.VideoWriter_fourcc(*'XVID')
out = cv2.VideoWriter('./photos/timelapse.avi', fourcc, 30, (320,240))


class SettingScrollOptions(SettingOptions):

    def _create_popup(self, instance):
        
        #global oORCA
        # create the popup
       
        content         = GridLayout(cols=1, spacing='5dp')
        scrollview      = ScrollView( do_scroll_x=False)
        scrollcontent   = GridLayout(cols=1,  spacing='5dp', size_hint=(None, None))
        scrollcontent.bind(minimum_height=scrollcontent.setter('height'))
        self.popup   = popup = Popup(content=content, title=self.title, 
			size_hint=(0.5, 0.9),  
			auto_dismiss=False)

        #we need to open the popup first to get the metrics 
        popup.open()
        #Add some space on top
        content.add_widget(Widget(size_hint_y=None, height=dp(2)))
        # add all the options
        uid = str(self.uid)
        for option in self.options:
            state = 'down' if option == self.value else 'normal'
            btn = ToggleButton(text=option, state=state, group=uid,
				size=(popup.width, dp(55)), 
				size_hint=(None, None))
            btn.bind(on_release=self._set_option)
            scrollcontent.add_widget(btn)

        # finally, add a cancel button to return on the previous panel
        scrollview.add_widget(scrollcontent)
        content.add_widget(scrollview)
        content.add_widget(SettingSpacer())
        #btn = Button(text='Cancel', size=((oORCA.iAppWidth/2)-sp(25), dp(50)),size_hint=(None, None))
        btn = Button(text='Cancel', size=(popup.width, dp(50)),size_hint=(0.9, None))
        btn.bind(on_release=popup.dismiss)
        content.add_widget(btn)


class TimerDropDown(DropDown):
	current_timer_modebtn = None
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.current_timer_modebtn = self.ids.timer_mode_off
	pass

class CameraScreenManager(ScreenManager):
	preview_on = False
	capturing_interval = False
	
	filter_index = -1
	filter_screens = {}
	
	current_timer_modebtn = None
	current_filter_modebtn = None
	current_camera_modebtn = None
	
	
	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		timerdropdown = ObjectProperty(None)
		self.timerdropdown = TimerDropDown()
		
		self.camera_display = Image(allow_stretch=True,
			keep_ratio=False)
		self.ids.camera_layer.add_widget(self.camera_display)
		
		self.transition_filter_screen('next')
		
		#Camera initialization
		self.camera, self.rawCapture = self.setup_camera()
		
		time.sleep(0.1)
		
		self.current_camera_modebtn = self.ids.camera_mode_photo
		self.set_camera_mode(self.current_camera_modebtn) #set initial mode to photo
		
		Logger.info("camera.py: Camera with resolution {0} w/ framerate of {1} successfully deployed."
			.format(self.camera.resolution, self.camera.framerate))
	
	#thread this?
	def setup_camera(self):
		config = App.get_running_app().config
		
		camera = PiCamera()
		camera.rotation = 180
		
		resolution_str = config.get('Camera', 'res')
		width, height = get_resolution(resolution_str)
		camera.resolution = (width,height)
		
		camera.framerate = config.getint('Camera','framerate')
		camera.brightness = config.getint('Camera','bright')
		camera.contrast = config.getint('Camera','contrast')
		camera.saturation = config.getint('Camera','saturation')
		camera.sharpness = config.getint('Camera', 'sharp')
		
		camera.exposure_mode = config.get('Camera', 'exposure').lower()
		camera.awb_mode = config.get('Camera','awb').lower()
		
		camera.led = config.getint('Camera', 'led')
		
		annotated = config.getint('Camera', 'annotated')
		if annotated:
			camera.annotate_text = config.get('Camera', 'text')
			camera.annotate_text_size = config.getint('Camera', 'text_size')
			camera.annotate_foreground = config.get('Camera', 'text_color')
			camera.annotate_background = config.get('Camera', 'background_color')
			
		rawCapture = PiRGBArray(camera, size=(width, height))
		return camera, rawCapture
	
	def set_camera_mode(self, button):
		if button.text == 'Square':
			self.ids.camera_layer.size_hint_x = None
			self.ids.camera_layer.width = self.ids.camera_layer.height
			width, height = self.camera.resolution
			width = height
			self.set_resolution(width, height)
		elif button.text != 'Square' and self.current_camera_modebtn.text == 'Square': #if previous mode is Square...
			self.ids.camera_layer.size_hint_x = 1
			resolution_str = App.get_running_app().config.get('Camera', 'res')
			width, height = get_resolution(resolution_str)
			self.set_resolution(width, height)
		self.current_camera_modebtn.color = (1,1,1,1)#unhighlight prev button
		button.color = (1,1,0.2,1) #highlight new button
		self.current_camera_modebtn = button
		self.current_camera_mode = button.text
		if not self.preview_on:
			self.preview_on = True
			self.thread = threading.Thread(target=self.display_preview)
			self.thread.start()
	
	def dropdown_open(self, instance):
		self.timerdropdown.open(instance)
		
	def set_timer(self, button, value):
		self.timerdropdown.current_timer_modebtn.background_color = (0.1, 0.1, 0.1, 0.8)  #unhighlight prev value
		button.background_color = (0, 1, 1, 0.75) #highlight selected value
		self.current_timer_modebtn = button
	
	def display_gallery(self):
		main_screen = Screen()
		screen_manager = ScreenManager(transition= NoTransition())
		sub_screen = Screen()
		scrollview = ScrollView(do_scroll_x=False)
		gridlayout = GridLayout(cols=4, spacing=20, padding=20,
			size_hint_y=None)
		gridlayout.bind(minimum_height=gridlayout.setter('height'))
		scrollview.add_widget(gridlayout)
		sub_screen.add_widget(scrollview)
		
		
		images = glob.glob('./photos/*.png')
		for image in images:
			button = Button(background_normal = image, 
				size_hint_y=None, height=200)
			button.bind(on_press=lambda btn: self.display_photo(screen_manager, sub_screen, btn))
			gridlayout.add_widget(button)
		videos = glob.glob('./photos/*.mp4')
		for video in videos:
			vid_player = VideoPlayer(source=video, size_hint_y=None,
				height=200)
			gridlayout.add_widget(vid_player)
		
		floatlayout = FloatLayout(size_hint_y=0.1)
		homebtn = Button(size_hint_x= 0.05,
			border=(0,0,0,0),
			pos_hint = {'center_x': 0.5, 'center_y': 0.5},
			background_normal= 'atlas://icons/camera_icons/home',
			on_press=lambda x: self.return_home(main_screen))	
		floatlayout.add_widget(homebtn)
		
		boxlayout = BoxLayout(orientation='vertical', spacing=20, padding=20)
		boxlayout.add_widget(screen_manager)
		boxlayout.add_widget(floatlayout)
		
		main_screen.add_widget(boxlayout)
		
		screen_manager.switch_to(sub_screen)
		self.switch_to(main_screen, direction='down')
		
	def display_photo(self, screen_manager, screen, button):
		photo_screen = Screen()
		button = Button(background_normal=button.background_normal,
			on_press= lambda x: screen_manager.switch_to(screen))
		photo_screen.add_widget(button)
		
		screen_manager.switch_to(photo_screen)

	def return_home(self, screen):
		self.switch_to(self.ids.main_screen, direction='up')
		self.remove_widget(screen)
	
	def load_filter_screen(self, index):
		if index in self.filter_screens:
			return self.filter_screens[index]
		else:
			screen = self.create_filter_screen(index)
			self.filter_screens[index] = screen
			return screen
	
	def create_filter_screen(self, index):
		screen = Screen(name = 'filter_page_' + str(index))
		gridlayout = GridLayout(cols=3, rows=3, spacing=20, padding=20)
		for i in range(9 * index, 9 + 9 * index):
			button = Button(text=image_effects[i], font_size=30, halign='right', valign='bottom')
			button.bind(size=button.setter('text_size'))
			button.color = (1,1,1,1)
			target = partial(self.set_filter_mode, image_effects[i])
			button.bind(on_press=target)
			gridlayout.add_widget(button)
			if image_effects[i] == 'none': #set initial mode to None
				self.current_filter_modebtn = button
				button.color = (1,1,0.2,1)
				
		screen.add_widget(gridlayout)
		return screen
		
	def transition_filter_screen(self, direction):
		if direction == 'next':
			self.filter_index = (self.filter_index + 1) % int((len(image_effects)/9))
			screen = self.load_filter_screen(self.filter_index)
			self.ids.filter_manager.switch_to(screen, direction='left')
		else:
			self.filter_index = (self.filter_index - 1) % int((len(image_effects)/9))
			screen = self.load_filter_screen(self.filter_index)
			self.ids.filter_manager.switch_to(screen, direction='right')
		
	
	def set_filter_mode(self, effect, button):
		self.current_filter_modebtn.color = (1,1,1,1)
		button.color = (1,1,0.2,1)
		self.current_filter_modebtn = button
		
		self.camera.image_effect = effect
		self.ids.screen_manager.current = 'cam_screen'
		self.ids.screen_manager.transition.direction = 'up'
		Logger.info("camera.py: Camera image effect has been set to {0}."
			.format(self.camera.image_effect))
		
	def display_preview(self):
		for frame in self.camera.capture_continuous(self.rawCapture, format="rgb", use_video_port=True):
			image = frame.array
			if self.preview_on:
				buf = cv2.flip(image, 0)
				buf = buf.tostring()
				self.create_texture(image, buf) #must do this in main thread
			else:
				self.rawCapture.truncate(0)
				break
			self.rawCapture.truncate(0)
				
	@mainthread
	def create_texture(self, image, buf):
		texture = Texture.create(size=(image.shape[1], image.shape[0]), colorfmt='rgb')
		texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
		self.camera_display.texture = texture
		
	def capture_interval(self, rawCapture, delay, mode):
		i = 0
		while self.capturing_interval:
			image = rawCapture.array
			image = image[..., ::-1]
			i += 1 
			cv2.imwrite('./photos/{0}/img{1}.jpg'.format(mode, i), image)
			time.sleep(delay)
	
	def capture(self):
		if self.current_camera_modebtn.text == 'Photo' or self.current_camera_modebtn.text == 'Square':
			self.camera.capture('./photos/image.jpg')
		elif self.current_camera_mode == 'Video':
			if not self.camera.recording: #start recording
				self.camera.start_recording('./photos/video.h264')
				Logger.info("camera.py: Camera is now recording in resolution {0} w/ framerate of {1} successfully deployed."
					.format(self.camera.resolution, self.camera.framerate))
			else: #stop recording
				self.camera.stop_recording()
				os.system('MP4Box -fps 30 -add photos/video.h264 photos/video.mp4')
				os.system('rm photos/video.h264')
				Logger.info("camera.py: Video successfully recorded and saved.")
			for child in self.ids.camera_mode_gridlayout.children:
					child.disabled = not child.disabled
		elif self.current_camera_modebtn.text == 'Slow-mo':
			if not self.camera.recording: #start recording
				self.camera.start_recording('./photos/slowmo.h264')
				Logger.info("camera.py: Camera is now recording in resolution {0} w/ framerate of {1} successfully deployed."
					.format(self.camera.resolution, self.camera.framerate))
			else:  #stop recording
				self.camera.stop_recording()
				os.system('MP4Box -fps 5 -add photos/slowmo.h264 photos/slowmo.mp4')
				os.system('rm photos/slowmo.h264')
				Logger.info("camera.py: Slow-mo video successfully recorded and saved.")
			for child in self.ids.camera_mode_gridlayout.children:
					child.disabled = not child.disabled
		elif self.current_camera_modebtn.text == 'Timelapse':
			if not self.capturing_interval:
				self.capturing_interval = True
				Logger.info("camera.py: Camera is now recording in resolution {0} w/ framerate of {1} successfully deployed."
					.format(self.camera.resolution, self.camera.framerate))
				timelapse_thread = threading.Thread(target=self.capture_interval,args = (self.rawCapture,5, 'timelapse'))
				timelapse_thread.start()
			else:
				self.capturing_interval = False
				images = sorted(glob.glob('./photos/timelapse/*.jpg'), key =os.path.getmtime)
				for image in images:
					frame = cv2.imread(image)
					out.write(frame)
				os.system('rm  ./photos/timelapse/*.jpg')
				Logger.info("camera.py: Timelapse video successfully recorded and saved.")
		elif self.current_camera_modebtn.text == 'Panaroma':
			if not self.capturing_interval:
				self.capturing_interval = True
				Logger.info("camera.py: Camera is now recording in resolution {0} w/ framerate of {1} successfully deployed."
					.format(self.camera.resolution, self.camera.framerate))
				panaroma_thread = threading.Thread(target=self.capture_interval,args = (self.rawCapture,2, 'panaroma'))
				panaroma_thread.start()
			else:
				self.capturing_interval = False
				images = sorted(glob.glob('./photos/temp/*.jpg'), key =os.path.getmtime)
				image_list = []
				for image in images:
					frame = cv2.imread(image)
					image_list.append(frame)
				Logger.info("camera.py: Now forming Panaroma photo. Please wait...")
				stitcher = cv2.createStitcher() if imutils.is_cv3() else cv2.Sticher_create()
				status, stitched = stitcher.stitch(image_list)
				if status == 0:
					cv2.imwrite('./photos/panaroma.jpg', stitched)
					Logger.info("camera.py: Panaroma photo successfully  transformed and saved.")
				else:
					Logger.info("camera.py: Failed to create Panaroma image.")
				os.system('rm  ./photos/panaroma/*.jpg')
				
	def set_resolution(self, width, height):
		if self.preview_on:
			self.preview_on = False
			self.thread.join()
			self.camera.resolution = (width,height)
			self.rawCapture.size = (width,height)
			self.preview_on = True
			self.thread = threading.Thread(target=self.display_preview)
			self.thread.start()
		else:
			self.camera.resolution = (width,height)
			self.rawCapture.size = (width,height)
	
class CameraApp(App):
	def build(self):
		self.settings_cls = SettingsWithSidebar
		self.use_kivy_settings = False
		return CameraScreenManager()
	
	def build_config(self, config):
		config.setdefaults('Camera',{'res' : '320x240',
			'format' : 'PNG',
			'framerate' : 30,
			'bright' : 50,
			'contrast' : 0,
			'saturation' : 0,
			'sharp' : 0,
			'exposure' : 'Auto',
			'awb' : 'Auto',
			'led' : 1,
			'annotated' : 0,
			'text' : '',
			'text_size' : 32,
			'text_color' : 'white',
			'background_color' : 'None'})
		
	def build_settings(self, settings):
		settings.register_type('scrolloptions', SettingScrollOptions)
		settings.add_json_panel('Camera', self.config, 'settings.json')
	
	def on_config_change(self, config, section, key, value):
		Logger.info("camera.py: App.on_config_change: {0}, {1}, {2}, {3}".format(
            config, section, key, value))
		if key == 'res':
			width, height = get_resolution(value)
			self.root.set_resolution(width,height)
			Logger.info("camera.py: Camera resolution has been set to {0}".format(
				self.root.camera.resolution))
		elif key == 'framerate':
			self.root.camera.framerate = int(value)
			Logger.info("camera.py: Camera framerate has been set to {0}".format(
            self.root.camera.framerate))
		elif key == 'bright':
			value = int(value)
			if (value < 0 or value > 100):
				value = 0 if value < 0 else 100
			self.root.camera.brightness = value
			Logger.info("camera.py: Camera brightness has been set to {0}".format(
				self.root.camera.brightness))
		elif key == 'contrast':
			value = int(value)
			if abs(value) > 100:
				value = -100 if value < -100 else 100
			self.root.camera.contrast = value
			Logger.info("camera.py: Camera contrast has been set to {0}".format(
				self.root.camera.contrast))
		elif key == 'saturation':
			value = int(value)
			if abs(value) > 100:
				value = -100 if value < -100 else 100
			self.root.camera.saturation = value
			Logger.info("camera.py: Camera saturation has been set to {0}".format(
				self.root.camera.saturation))
		elif key == 'sharp':
			value = int(value)
			if abs(value) > 100:
				value = -100 if value < -100 else 100
			self.root.camera.sharpness = value
			Logger.info("camera.py: Camera sharpness has been set to {0}".format(
				self.root.camera.sharpness))
		elif key == 'exposure':
			self.root.camera.exposure_mode = value.lower()
			Logger.info("camera.py: Camera exposure mode has been set to {0}".format(
				self.root.camera.exposure_mode))
		elif key == 'awb':
			self.root.camera.awb_mode = value.lower()
			Logger.info("camera.py: Camera awb mode has been set to {0}".format(
				self.root.camera.awb_mode))
		elif key == 'led':
			self.root.camera.led = int(value)
			Logger.info("camera.py: Camera led has been set to {0}".format(
				value))
		elif key == 'annotated':
			with open('settings.json', 'r+') as jsonF:
				data = json.load(jsonF)
				
				for i in range (10,14):
					data[i]['disabled'] = not int(value)
				
				jsonF.seek(0)
				json.dump(data, jsonF, indent=4)
				jsonF.truncate()
				jsonF.close()
			Logger.info("camera.py: Camera settings is now closing for new changes to take place...")
			time.sleep(10)
			self.close_settings()
			self.destroy_settings()
			Logger.info("camera.py: Camera text annotation has been set to {0}".format(
				value))
		elif key == 'text' and self.config.getint('Camera', 'annotated'):
			self.root.camera.annotate_text = int(value)
			Logger.info("camera.py: Camera text has been set to '{0}'".format(
				value))
		elif key == 'text_size' and self.config.getint('Camera', 'annotated'):
			value = int(value)
			if(value < 6 or value > 160):
				value = 6 if value < 6 else 160
			self.root.camera.annotate_text_size = value
			Logger.info("camera.py: Camera text size has been set to {0}".format(
				value))
		elif key == 'text_color' and self.config.getint('Camera', 'annotated'):
			self.root.camera.annotate_foreground = value
			Logger.info("camera.py: Camera text color has been set to {0}".format(
				value))
		elif key == 'background_color' and self.config.getint('Camera', 'annotated'):
			self.root.camera.annotate_background = value
			Logger.info("camera.py: Camera background color has been set to {0}".format(
				value))
				
def get_resolution(string):
	string = string.split('x')
	width = int(string[0])
	height = int(string[1])
	return width, height

if __name__ == '__main__':
	CameraApp().run()