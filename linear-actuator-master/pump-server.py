#!/usr/bin/python3

# Copyright 2013 Michigan Technological University
# Author: Bas Wijnen <bwijnen@mtu.edu>
# This design was developed as part of a project with
# the Michigan Tech Open Sustainability Technology Research Group
# http://www.appropedia.org/Category:MOST
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or(at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import fhs
import websocketd
import sys
import time
try:
	import RPi.GPIO as gpio
	gpio.setwarnings(False)
	gpio.setmode(gpio.BOARD)
except:
	sys.stderr.write('Warning: using emulation because RPi.GPIO could not be used\n')
	class gpio:
		LOW = 0
		HIGH = 1
		IN = 0
		OUT = 1
		@classmethod
		def output(cls, pin, state):
			pass
		@classmethod
		def setup(cls, pin, type, initial):
			pass

config = fhs.init(packagename = 'pump-server', config = {
	'port': '8888',
	'address': '0.0.0.0',	# Force IPv4, because Raspberry Pi chokes on IPv6.
	'pitch': .8,
	'steps-per-revolution': 3200, # Per Microstep(1/16 of the full step)
	'initial-ml-per-s': .7, #max 2.3
	'initial-ml-per-mm': 0.4,
	'dir-pin': 3,  # Original Pin 11 Dead
	'step-pin': 13,
	'sleep-pin': 5, # original pin 15 Dead
	'ms3-pin': 19,
	'ms2-pin': 21,
	'ms1-pin': 23,
        'en-pin' : 5,
	'login': '',
	'passwordfile': '' })

DIR = int(config['dir-pin'])
STEP = int(config['step-pin'])
SLEEP = int(config['sleep-pin'])
MS3 = int(config['ms3-pin'])
MS2 = int(config['ms2-pin'])
MS1 = int(config['ms1-pin'])
gpio.setup(SLEEP, gpio.OUT, initial = gpio.HIGH)
gpio.setup(STEP, gpio.OUT, initial = gpio.HIGH)
gpio.setup(DIR, gpio.OUT, initial = gpio.HIGH)
gpio.setup(MS1, gpio.OUT, initial = gpio.HIGH)
gpio.setup(MS2, gpio.OUT, initial = gpio.HIGH)
gpio.setup(MS3, gpio.OUT, initial = gpio.HIGH)

pitch = float(config['pitch'])
steps = float(config['steps-per-revolution'])
initial_ml_per_s = float(config['initial-ml-per-s'])
initial_ml_per_mm = float(config['initial-ml-per-mm'])

class Pump:
	def __init__(self):
		self.position = 0.
		self.steps_per_mm = steps / pitch
		self.ml_per_s = initial_ml_per_s
		self.ml_per_mm = initial_ml_per_mm
	def calibrate(self, ml_per_mm):
		self.ml_per_mm = ml_per_mm * 1.
		notify('calibration', self.ml_per_mm)
	def setposition(self, position):
		self.position = position
		notify('position', self.position)
	def goto(self, ml):
		self.move(ml - self.position)
	def move(self, ml):
		print("Starting to move "+str(ml)+"ml")
		gpio.output(SLEEP, gpio.HIGH)
		gpio.output(DIR, gpio.LOW if ml < 0 else gpio.HIGH)
		notify('move', self.position, ml)
		# ml/mm
		# ml/s
		# step/mm
		#s_per_half_step=0.001
		# s/step ?
		s_per_half_step = self.ml_per_mm / self.steps_per_mm / self.ml_per_s / 2
		
		steps = int(ml / self.ml_per_mm * self.steps_per_mm + .5)
		print("Half Step(s) - "+str(s_per_half_step))
		print("No of Steps(push is positive) - "+str(steps))
		target = time.time()
		for t in range(abs(steps)):
			gpio.output(STEP, gpio.HIGH)
			target += s_per_half_step
			while time.time() < target:
				# Yes, this is a busy wait.
				pass
			gpio.output(STEP, gpio.LOW)
			target += s_per_half_step
			while time.time() < target:
				# Yes, this is a busy wait.
				pass
		self.position += ml
		notify('position', self.position)

		self.sleep()# make the motor sleep for overheat prevention
		
	def speed(self, ml_per_s):
		self.ml_per_s = ml_per_s
		notify('speed', ml_per_s)
	def sleep(self):
		gpio.output(SLEEP, gpio.LOW)

users = set()

def send(socket, cmd, *arg):
	getattr(socket, cmd)(*arg)
def notify(cmd, *arg):
	for u in users:
		send(u, cmd, *arg)

p = Pump()

class Connection:
	def __init__(self, socket):
		self.socket = socket
	def monitor(self):
		users.add(self.socket)
		send(self.socket, 'calibration', p.ml_per_mm)
		send(self.socket, 'position', p.position)
		send(self.socket, 'speed', p.ml_per_s)
	def __getattr__(self, attr):
		return getattr(p, attr)

def disconnect(socket):
	if socket in users:
		users.remove(socket)

class Server(websocketd.RPChttpd):
	def auth_message(self, connection, is_websocket):
		return 'Please identify yourself' if config['passwordfile'] or config['login'] else None
	def authenticate(self, connection):
		if config['login']:
			if ':' in config['login']:
				user, password = config['login'].split(':', 1)
				if user == connection.data['user'] and password == connection.data['password']:
					return True
			else:
				if connection.data['user'] == config['login']:
					return True
		if config['passwordfile']:
			with open(config['passwordfile']) as f:
				for l in f:
					if ':' not in l:
						continue
					user, password = l.split(':')[:2]
					if user == connection.data['user'] and(password[1:] == connection.data['password'] if password.startswith(':') else password == crypt.crypt(connection.data['password'], password)):
						return True
		return False

# Use address to avoid listening on IPv6, otherwise it fails to work on a Raspberry Pi.
print('START')
s = Server(config['port'], address = config['address'], httpdirs = fhs.read_data('html', dir = True, multiple = True), target = Connection, disconnect_cb = disconnect)

websocketd.fgloop()
print('FINISH')
