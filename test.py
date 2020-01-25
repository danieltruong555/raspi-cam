from picamera import PiCamera
import time

camera = PiCamera()
camera.resolution = (80,60)
camera.rotation = 180
camera.start_preview()
for effect in camera.IMAGE_EFFECTS:
	camera.image_effect = effect
	time.sleep(5)
	camera.capture('./icons/filter/' + effect + '.png')
camera.stop_preview()
camera.close()