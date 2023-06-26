# Flask-web-game
A Python web app made using the Flask-SocketIO module for server-client communication. 
Multiple clients can connect to the server. Clients can communicate with each other using a text chat, join two-person rooms and play a game of dice within these rooms. 

## Server
The server is a Python application made using Flask-SocketIO and Flask modules. It reacts and responds to client requests. The server also sends data to clients without client's request. The server holds all of data regarding users (e.g. uernames, IDs, passwords). The server executes game's logic and operations related to the game.
Actions regarding sockets are executed in the main thread of the application. Game-related actions are executed in the background thread.

## Client
Client application is a browser HTML application which uses Javascripts with jQuery and socket.io libraries. Client application serves the purpose of a GUI to the functionalities offered by the server.

![image](https://github.com/mickol111/Flask-web-game/assets/22640141/d33a7c52-a009-4df8-88f0-e8c4091fe705)
<i>Fig.1. Client application.</i>

