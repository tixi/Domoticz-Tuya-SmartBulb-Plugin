########################################################################################
# 	Domoticz Tuya Smart Bulb Python Plugin                                             #
#                                                                                      #
# 	MIT License                                                                        #
#                                                                                      #
#	Copyright (c) 2018 tixi                                                            #
#                                                                                      #
#	Permission is hereby granted, free of charge, to any person obtaining a copy       #
#	of this software and associated documentation files (the "Software"), to deal      #
#	in the Software without restriction, including without limitation the rights       #
#	to use, copy, modify, merge, publish, distribute, sublicense, and/or sell          #
#	copies of the Software, and to permit persons to whom the Software is              #
#	furnished to do so, subject to the following conditions:                           #
#                                                                                      #
#	The above copyright notice and this permission notice shall be included in all     #
#	copies or substantial portions of the Software.                                    #
#                                                                                      #
#	THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR         #
#	IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,           #
#	FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE        #
#	AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER             #
#	LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,      #
#	OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE      #
#	SOFTWARE.                                                                          #
#                                                                                      #
########################################################################################

"""
<plugin key="tixi_tuya_smartbulb_plugin" name="Tuya SmartBulb" author="tixi" version="1.0.1" externallink=" https://github.com/tixi/Domoticz-Tuya-SmartBulb-Plugin">
	<params>
		<param field="Address" label="IP address" width="200px" required="true"/>
		<param field="Mode1" label="DevID" width="200px" required="true"/>
		<param field="Mode2" label="Local Key" width="200px" required="true"/>
		<param field="Mode6" label="Debug" width="75px">
			<options>
				<option label="True" value="Debug"/>
				<option label="False" value="Normal" default="true"/>
			</options>
		</param>
	</params>
</plugin>
"""

import Domoticz
import pytuya
import json

class BasePlugin:
	
	__UNIT                  = 1
	__HB_BASE_FREQ          = 6

	__DPS_INDEX_ON          = '1'
	__DPS_INDEX_MODE        = '2'
	__DPS_INDEX_BRIGHTNESS  = '3'
	__DPS_INDEX_COLOUR      = '5'
	
	__DPS_MODE_WHITE        = 'white'
	__DPS_MODE_COLOUR       = 'colour'

	#__NEEDED_DPS_INDEX = (self.__DPS_INDEX_ON,self.__DPS_INDEX_MODE,self.__DPS_INDEX_BRIGHTNESS,self.__DPS_INDEX_COLOUR)
	__NEEDED_DPS_INDEX = ('1','2','3','5')
	
	def __init__(self):
		self.__address      = None          		#IP address of the smartbulb
		self.__devID        = None          		#devID of the smartbulb
		self.__localKey     = None          		#localKey of the smartbulb
		self.__device       = None          		#pytuya object of the smartbulb
		self.__runAgain     = self.__HB_BASE_FREQ	#heartbeat frequency (60 seconds)
		self.__connection   = None					#connection to the tuya bulb
		self.__last_payload = None          		#last payload (None/'status'/dict payload)
		
		return
		
	#onStart Domoticz function
	def onStart(self):
		
		# Debug mode
		if(Parameters["Mode6"] == "Debug"):
			Domoticz.Debugging(1)
			Domoticz.Debug("onStart called")
		else:
			Domoticz.Debugging(0)
			
		#get parameters
		self.__address  = Parameters["Address"]
		self.__devID    = Parameters["Mode1"]
		self.__localKey = Parameters["Mode2"]
			
		#initialize the defined device in Domoticz
		if (len(Devices) == 0):
			Domoticz.Device(Name="Tuya SmartBulb", Unit=1, Type=241, Subtype=2, Switchtype=7).Create()
			Domoticz.Log("Tuya SmartBulb Device created.")
		
		#create the pytuya object
		self.__device = pytuya.BulbDevice(self.__devID, self.__address, self.__localKey)

		#start the connection
		self.__last_payload = 'status'
		self.__connection   = Domoticz.Connection(Name="Tuya", Transport="TCP/IP", Address=self.__address, Port="6668")
		self.__connection.Connect()

	def onConnect(self, Connection, Status, Description):
		if (Connection == self.__connection):
			if (Status == 0):
				Domoticz.Debug("Connected successfully to: "+Connection.Address+":"+Connection.Port)
				if(self.__last_payload != None):
					self.__payload_to_execute(self.__last_payload)
			else:
				Domoticz.Debug("OnConnect Error Status: " + str(Status))
				if(Status==113):#no route to host error (skip to avoid intempestive connect call)
					return
				if(self.__connection.Connected()):
					self.__connection.Disconnect()
				if(not self.__connection.Connecting()):
					self.__connection.Connect()
				


	def __extract_state(self, Data):
		""" Returns a tuple (bool,dict) 
			first:  set to True if an error occur and False otherwise
			second: dict dps state
			
			second is irrelevant if first is True 
		"""
		start=Data.find(b'{"devId')
		
		if(start==-1):
			return (True,"")
			
		result = Data[start:] #in 2 steps to deal with the case where '}}' is present before {"devId'
			
		end=result.find(b'}}')
		
		if(end==-1):
			return (True,"")
		
		end=end+2
		result = result[:end]
		if not isinstance(result, str):
			result = result.decode()
			
		try:
			result = json.loads(result)
			
			for val in self.__NEEDED_DPS_INDEX:
				if(val not in result['dps']):
					return (True,"")
			
			return (False,result['dps'])
		except (JSONError, KeyError) as e:
			return (True,"")

	def onMessage(self, Connection, Data):
		Domoticz.Debug("onMessage called: " + Connection.Address + ":" + Connection.Port +" "+ str(Data))
		
		if (Connection == self.__connection):
			
			if(self.__last_payload == None):#skip nothing was waiting
				return
			
			(error,state) = self.__extract_state(Data)
			if(error):
				self.__payload_to_execute(self.__last_payload)
				return

			#update device
			if(state[self.__DPS_INDEX_ON]):#on
				c_level=state[self.__DPS_INDEX_BRIGHTNESS]
				level=((c_level-25)*100)/230 #scale from 25-255 to 1-100
				UpdateDevice(self.__UNIT, 1, level)
			else:
				UpdateDevice(self.__UNIT, 0, "Off")

			#check if replay is needed
			if(self.__last_payload == 'status'):
				self.__last_payload = None
				return
			
			#dict payload
			error = False
			for val in self.__last_payload.keys():
				if(self.__last_payload[val] != state[val]):
					error = True
			
			if(error):
				self.__payload_to_execute(self.__last_payload)
			else:
				self.__last_payload = None


	def __payload_to_execute(self,payload):
		
		#The validity of the payload is not checked in this function
			
		if(payload=='status'):
			if(self.__last_payload == None):
				self.__last_payload = payload
				
		else:#dict payload
			self.__last_payload = payload
		
		if(self.__connection.Connected()):
			if(payload != 'status'):
				payload = self.__device.generate_payload('set', payload)
				self.__connection.Send(payload)
			payload=self.__device.generate_payload('status')
			self.__connection.Send(payload)
		else:
			if(not self.__connection.Connecting()):
				self.__connection.Connect()
			

	def onCommand(self, Unit, Command, Level, Hue):
		Domoticz.Debug("onCommand called for Unit " + str(Unit) + ": Parameter '" + str(Command) + "', Level: " + str(Level) + "', Hue: " + str(Hue))
				
		payload = {}
		if(Command == 'Off'):
			payload[self.__DPS_INDEX_ON] = False
			self.__payload_to_execute(payload)
			return
		
		payload[self.__DPS_INDEX_ON] = True #force On needed in some case.
		
		if(Command == "On"):
			payload[self.__DPS_INDEX_ON] = True
		
		elif(Command == "Set Level"):
			c_level                              = int((Level * 230)/100 +25) #scale from 0-100 to 25-255
			payload[self.__DPS_INDEX_MODE]       = self.__DPS_MODE_WHITE #force to white
			payload[self.__DPS_INDEX_BRIGHTNESS] = c_level

		elif(Command == "Set Color"):
			color_info=json.loads(Hue)
			r=color_info["r"]
			g=color_info["g"]
			b=color_info["b"]
			m=color_info["m"]
		
			if(m==1 or (m==3 and r==255 and g==255 and b==255) ):#white
				c_level=int((Level * 230)/100 +25)
					
				payload[self.__DPS_INDEX_MODE]       = self.__DPS_MODE_WHITE
				payload[self.__DPS_INDEX_BRIGHTNESS] = c_level
		
			elif(m==3):
				payload[self.__DPS_INDEX_MODE]   = self.__DPS_MODE_COLOUR
				payload[self.__DPS_INDEX_COLOUR] = self.__device._rgb_to_hexvalue(r, g, b)
			else:
				Domoticz.Error("Invalid mode to set the color")
				return
				
		elif(Command == "Set Full"):
			payload[self.__DPS_INDEX_MODE]       = self.__DPS_MODE_WHITE
			payload[self.__DPS_INDEX_BRIGHTNESS] = 255
			
		elif(Command == "Set Night"):
			payload[self.__DPS_INDEX_MODE]       = self.__DPS_MODE_WHITE
			payload[self.__DPS_INDEX_BRIGHTNESS] = 25
		
		else:
			Domoticz.Error("Undefined command: " + Command)
			return
		
		self.__payload_to_execute(payload)
		

	def onDisconnect(self, Connection):
		Domoticz.Debug("Disconnected from: "+Connection.Address+":"+Connection.Port)

	def onHeartbeat(self):
		self.__runAgain -= 1
		if(self.__runAgain == 0):
			self.__runAgain = self.__HB_BASE_FREQ				
			self.__payload_to_execute('status')
	
	#onStop Domoticz function
	def onStop(self):
		self.__device       = None
		self.__last_payload = None
		if(self.__connection.Connected()):
			self.__connection.Disconnect()
		self.__connection   = None

global _plugin
_plugin = BasePlugin()

def onStart():
	global _plugin
	_plugin.onStart()

def onStop():
	global _plugin
	_plugin.onStop()

def onConnect(Connection, Status, Description):
	global _plugin
	_plugin.onConnect(Connection, Status, Description)

def onMessage(Connection, Data):
	global _plugin
	_plugin.onMessage(Connection, Data)

def onCommand(Unit, Command, Level, Hue):
	global _plugin
	_plugin.onCommand(Unit, Command, Level, Hue)

def onDisconnect(Connection):
	global _plugin
	_plugin.onDisconnect(Connection)

def onHeartbeat():
	global _plugin
	_plugin.onHeartbeat()

################################################################################
# Generic helper functions
################################################################################

def UpdateDevice(Unit, nValue, sValue, TimedOut=0, AlwaysUpdate=False):
	# Make sure that the Domoticz device still exists (they can be deleted) before updating it
	if Unit in Devices:
		if Devices[Unit].nValue != nValue or Devices[Unit].sValue != sValue or Devices[Unit].TimedOut != TimedOut or AlwaysUpdate:
			Devices[Unit].Update(nValue=nValue, sValue=str(sValue), TimedOut=TimedOut)
			Domoticz.Debug("Update " + Devices[Unit].Name + ": " + str(nValue) + " - '" + str(sValue) + "'")
