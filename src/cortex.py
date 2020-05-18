import asyncio
import websockets
import ssl
import pathlib
import json

class Cortex:
	def __init__(self, clientId, secretId, uri):
		self.clientId = clientId
		self.secretId = secretId
		self.authorizationToken = None
		self.uri = uri
		self.headsetId = None
		self.headsetStatus = None
		self.sessionId = None
		self.sessionIdRecord = []
		self.websocket = None
		self.count = 0

	async def init_connection(self):
		ssl_context = ssl.create_default_context()
		ssl_context.check_hostname = False
		ssl_context.verify_mode = ssl.CERT_NONE
		self.websocket = await websockets.connect(self.uri, ssl = ssl_context)

	# Generate the JSON request following the structure required by the Cortex service 
    # Parameter method describes the Cortex API method intended to be called
    # Parameter **kwargs used to pass a variable-length argument list | It allows to pass keywork arguments
	def generateRequest(self, method, **kwargs):
		params = {key : value for (key, value) in kwargs.items()}
		request = json.dumps({
				"id" : 1,
				"jsonrpc" : "2.0",
				"method" : method,
				"params" : params
		})
		return request

	# Send the generated request through a web socket using the WebSocket secure protocol to Cortex 
	async def sendRequest(self, request):
		#async with websockets.connect(self.uri, ssl = ssl_context) as websocket:
		if not self.websocket:
			await self.init_connection()
			
		await self.websocket.send(request)
		response = await self.websocket.recv()
		response = json.loads(response)

		return response

	# Process brain data sent by Cortex Api
	async def receiveData(self):
		if self.count > 5:
			response = await self.websocket.recv()
			response = json.loads(response)
			self.count = 0
			return response
		else:
			self.count += 1
		return []

	# Receives training events
	async def receiveTrainingData(self):
		if self.count > 10:
			response = await self.websocket.recv()
			response = json.loads(response)
			print(response)
			return response["sys"][1]
			self.count = 0
		else:
			self.count += 1
		return 

	async def requestAccess(self):
		request = self.generateRequest("requestAccess", clientId = self.clientId, clientSecret = self.secretId)
		response = await self.sendRequest(request)
		print(response["result"]["message"])
		return

	# Generate Cortex access token which is required to use the Cortex API by the application
	async def getAuthorizationToken(self):
		request = self.generateRequest("authorize", clientId = self.clientId, clientSecret = self.secretId)
		response = await self.sendRequest(request)
		self.authorizationToken = response["result"]["cortexToken"]
		print("A Cortex access token has been generated")
		return 

	# Shows details of any headset connected to the device
	# It checks if there are headsets connected to the application and their status
	# No headsets connected ? It then shows the headsets and their status next to Computer
	async def queryHeadsets(self):
		if self.headsetId == None:
			request = self.generateRequest("queryHeadsets")
			response = await self.sendRequest(request) 
			self.headsetId = response["result"][0]["id"]
			self.headsetStatus = response["result"][0]["status"]
			message = "Headset's " + self.headsetId + " status is: " +self.headsetStatus
		
			
		else:
			request = self.generateRequest("queryHeadsets", id = self.headsetId)
			response = await self.sendRequest(request)
			self.headsetStatus = response["result"][0]["status"]
			message = "Headset's " + self.headsetId + " status is: " +self.headsetStatus
		
		return message

 	# Connects or disconnects a headset. It also refresh the list of available Bluetooth headsets returned by queryHeadsets
 	# Parameter mode can be: connect, disconnect and refresh
	async def actionOnHeadset(self, mode):
		if self.headsetId == None:
			return "Headset not paired"
		else:
			request = self.generateRequest("controlDevice", command = mode, headset = self.headsetId)
			response = await self.sendRequest(request)
			if mode == "connect":
				self.headsetStatus = "connected"
			elif mode == "disconnect":
				self.headsetStatus = "disconnected"

			return response["result"]["message"]

	# A session is an object that makes the link between the application and an EMOTIV headset.
	# IT IS MANDATORY to create a session before using the headset
	# A session is a temporary in-memory object, it is destroyed when the headset is disconnected or the application is being closed

	# Create a session
	# To create a session it is necessary to have a headset connected to the application
	async def createSession(self, status):
		if self.headsetStatus == "connected":
			request = self.generateRequest("createSession", cortexToken = self.authorizationToken,  headset = self.headsetId, status = status)
			response = await self.sendRequest(request)
			sessionStatus = response["result"]["status"]
			self.sessionId = response["result"]["id"]
			print("Session's status is: " + sessionStatus)
		else:
			print("Headset not connected, please connect to create a session!")
		
		return 

 	# Return the list of sessions created by the application
	async def querySessions(self):
		request = self.generateRequest("querySessions", cortexToken = self.authorizationToken)
		response = await self.sendRequest(request)
		print(response)
		#return response["result"]
		return

	async def updateSession(self):
		request = self.generateRequest("updateSession", cortexToken = self.authorizationToken, session = self.sessionId, status = "active")
		response = await self.sendRequest(request)
		#print(response)
		return

	async def hasAccessRight(self):
		request = self.generateRequest("hasAccessRight", clientId = self.clientId, clientSecret = self.secretId)
		response = await self.sendRequest(request)
		print(response["result"]["message"])
		return
	# Subscribe to one or more data streams, Cortex API will send through the web socket the type of data stated
	# Parameter stream can be: sys: Training of the mental commnads | eeg = RAW EEG | com = MENTAL COMMANDS DETECTION | mot = MOTION DATA | dev = DATA FROM HEADSET

	# After a successful subscription Cortex will keep sending data sample objects 
	# data sample object structure for mental commands
	# "success" : [{"cols": ["act", "pow"], "sid": "XXXX", "streamName": "com", "time": epoch}]
	# act = action e.g Push ! pow = power of the action e.g 0.382   0 <= x < 1 low power x = 1 high power
	async def subscribe(self, stream):
		request = self.generateRequest("subscribe", cortexToken = self.authorizationToken, session = self.sessionId, streams = stream)
		response = await self.sendRequest(request)
		return response

	# Cancel a subscription that was created by the subscribe method
	async def unsubscribe(self, stream):
		request = self.generateRequest("unsubscribe", cortexToken = self.authorizationToken,  session = self.sessionId, streams = stream)
		response = await self.sendRequest(request)
		print(response)
		return

	# After creating a session it is possible to create a record to permanently store data from a headset | You can associate a subject to a record
    # Create a record
	async def createRecord(self, title, description, subjectName, **kwargs):
		recordInfo = {}
		request = self.generateRequest("createRecord", session = self.sessionId, title = title, description = description, subjectName = subjectName, tags = None, experimentId = None)
		response = await self.sendRequest(request)
		self.sessionIdRecord.append(response["response"]["sessionId"])
		print("Record associated with record sessionId: " + response["result"]["sessionId"])
		for key, value in response["result"]["record"]:
			recordInfo[key] = value

		return recordInfo

	# Stop a record that was previously started by the createRecord method
	async def stopRecord(self, sessionIdRecord):
		recordInfo = {}
		request = self.generateRequest("stopRecord", session = sessionIdRecord)
		response = await self.sendRequest(request)
		print("Record with sessionId: " +response["result"]["sessionId"] + "stopped")
		for key, value in response["result"]["record"].items():
			recordInfo[key] = value
		
		recordInfo["sessionId"] = response["result"]["sessionId"]
		return recordInfo

	# Update record's info
	async def updateRecord(self, sessionIdRecord, description, tags):
		recordInfo = {}
		request = self.generateRequest("updateRecord", record = sessionIdRecord, description = description, tags = tags)
		response = await self.sendRequest(request)
		print("Record with record sessionId: " +self.sessionIdRecord)
		for key, value in response["result"].items():
			recordInfo[key] = value
		return recordInfo

	# Delete records previously created
	# Parameter records contain the record ids you want to delete					
	async def deleteRecord(self, records):
		request = self.generateRequest("deleteRecord", records = records)
		response = await self.sendRequest(request)
		if len(response["result"]["success"]) != 0:
			print("Records successfuly deleted")
		else:
			print(request["result"]["failure"])
		return 

	# Export one or more records to EDF or CSV format
	# Must stop record before exporting it
	# Data streams available: EEG, MOTION, PM(Performance metrics), BP(Band Powers)
	# format available: EDF | CSV
	async def exportRecord(self, sessionIdRecord, folder, streamTypes, formatRecord):
		request = self.generateRequest("exportRecord", cortexToken = self.authorizationToken, recordIds = sessionIdRecord, folder = folder, streamTypes = streamTypes, format = formatRecord)
		response = await self.sendRequest(request)
		if len(response["result"]["success"] != 0):
			print("Record: " +response["result"]["success"]["recordId"] + "has been exported successfuly")
		else:
			print("FAILURE...Record: " +response["result"]["failure"]["recordId"] + " error code: " +response["result"]["failure"]["code"])

		return 

	# query parameters is a query object that can have the following fields: licenseId, applcationId etc...
	# orderBy name of record field you want to order by : ASC | DESC
	async def queryRecords(self, query, orderBy):
		request = self.generateRequest("queryRecords", cortexToken = self.authorizationToken, query = query, orderBy = orderBy)
		response = await self.sendRequest(request)
		return response["result"]["records"]

	# A subject represents a human being or alien who is the subject of the record
	# Create a new subject | You can associate the subject to record when you call createRecord()
	async def createSubject(self, subjectName):
		request = self.generateRequest("createSubject", cortexToken = self.authorizationToken, subjectName = subjectName)
		response = await self.sendRequest(request)
		print("Subject created")
		return response["result"]["subjectName"]

	# async def updateSubject(self, subjectName):
	# 	request = self.generateRequest("updateSubject", subjectName = subjectName)		

	# Delete one or more subjects | This action is IRREVERSIBLE
	# Parameter subjects is  a list containg the subject's names
	async def deleteSubject(self, subjects):
		request = self.generateRequest("deleteSubject", subjects = subjects)
		response = await self.sendRequest(request)
		if len(response["result"]["success"] != 0):
			print("Subject " + response["result"]["success"]["subjectName"] + "deleted")
		else:
			print(response["result"]["failure"])
		return

	async def getDemographics(self):
		request = self.generateRequest("getDemographicAttributes", cortexToken = self.authorizationToken)
		response = await self.sendRequest(request)
		for element in response["result"]["attributes"]:
			print(element)
	# To use mental commands detection must load a training profile that contains training data
	# A profile is a persistent object that stores training data for mental command detections
	# A profile belongs to a user

	# Return list of all the training profiles of the user	
	async def queryProfile(self):
		request = self.generateRequest("queryProfile", cortexToken = self.authorizationToken)
		response = await self.sendRequest(request)
		for element in response["result"]:
			print(element["name"])
		return

	# Manage the traning profiles of the users
	# status can be: create, load, unload, save, rename, delete
	# Save profile after completing training or after changing attributes of the profile
	# Parameter profile contains the name of the profile
	# Parameter newProfileName is not empty if the status is rename
	async def setupProfile(self, profile, status):
		profile = profile.strip()
		request = self.generateRequest("setupProfile", cortexToken = self.authorizationToken, status = status, profile = profile, headset = self.headsetId)
		response = await self.sendRequest(request)
		self.saveProfile(profile)
		print(response["result"])
		return

	async def getCurrentProfile(self):
		request = self.generateRequest("getCurrentProfile", cortexToken = self.authorizationToken, headset = self.headsetId)
		response = await self.sendRequest(request)
		#print(response)
		return response

	async def unloadProfile(self):
		request = self.generateRequest("setupProfile", cortexToken = self.authorizationToken, status = "unload", profile="Santiago", headset = self.headsetId)
		response = await self.sendRequest(request)
		print(response)
		return 

	async def saveProfile(self, profile):
		request = self.generateRequest("setupProfile", cortexToken = self.authorizationToken, status = "save", profile = profile, headset = self.headsetId)
		response = await self.sendRequest(request)
		return

	# Return information about the mental command training or the facial expression training			
	async def getDetectionInfo(self, detection):
		request  = self.generateRequest("getDetectionInfo", detection = detection)
		response = await self.sendRequest(request)
		print(response["result"])
		return

	# TRAINING WORKFLOW:
	# 1) Subscribe to data stream 'sys'
	# 2) Start training by calling training() with the action to be trained and control "start"
	# 2 1/2) Call training() with control "reset" to redo the last training
	# 3) Received event "succeded" or "failed"
	# 4) Call training() with control "accept" to accept training or "reject" to reject the training
	# 5) Save profile to keep training

	# Control the training of the mental command
	# detection can be: mentalCommand or facialExpression
	# status can be: start, accept, reject, reset = cancel the current training, erase = Erase all the training data for the specified action
	# action can be: neutral, list, drop, left, right
	async def training(self, detection, status, action):
		request = self.generateRequest("training", cortexToken = self.authorizationToken, session = self.sessionId, detection = detection , status = status, action = action)
		response = await self.sendRequest(request)
		print(response)
		return

	# Return list of trained actions of a profile and how many times the user trained this action		

	async def getTrainedSignatureActions(self, detection, profile):
		request = self.generateRequest("getTrainedSignatureActions", cortexToken = self.authorizationToken, detection = detection, profile = profile)
		response = await self.sendRequest(request)
		return response
		

	# Set or get the active actions for the mental command detection
	# set can be: set or get
	# If action is set then the parameter actions is a list containing the list of actions to activate
	async def mentalCommandActiveAction(self, status, profile, actions):
		request = self.generateRequest("mentalCommandActiveAction", cortexToken = self.authorizationToken, status = status, profile = profile, session = self.sessionId, actions = actions)
		response = await self.sendRequest(request)
		return response


	# # Return brain map of a profile with coordinates
	# async def mentalCommandBrainMap(self, profile):
	# 	brainMap = {}
	# 	request = self.generateRequest("mentalCommandBrainMap", cortexToken = self.authorizationToken, profile = profile, session = self.sessionId)
	# 	response = await self.sendRequest(request)
	# 	for element in response["result"]:
	# 		brainMap[element["action"]] = element["coordinates"]

	# 	return brainMap

	# Return skill rating of a mental command action
	# If parameter action is empty then it returns the overall mental command skill rating			
	async def mentalCommandGetSkillRating(self, profile, action):
		request = self.generateRequest("mentalCommandGetSkillRating", cortexToken = self.authorizationToken, profile = profile, session = self.sessionId, action = action)
		response = await self.sendRequest(request)
		return response["result"]

	# Return the current threshold of the mental command detection and the score of the last mental command training	
	async def mentalCommandTrainingThreshold(self, profile):
		request = self.generateRequest("mentalCommandTrainingThreshold", cortexToken = self.authorizationToken, profile = profile)
		response = await self.sendRequest(request)
		return response
		#return response["result"]["lastTrainingScore"]

	# Set or get the action level of the mental command detection
	async def mentalCommandActionLevel(self, status, profile, level):
		request = self.generateRequest("mentalCommandActionLevel", cortexToken = self.authorizationToken, status = status, profile = profile, session = self.sessionId, level = level)
		response = await self.sendRequest(request)
		return response

	def close(self):
		self.websocket.close()