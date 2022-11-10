from threading import Lock
from flask import Flask, render_template, session, request, \
    copy_current_request_context
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, call, disconnect,send

import random

# Set this variable to "threading", "eventlet" or "gevent" to test the
# different async modes, or leave it set to None for the application to choose
# the best option based on installed packages.
async_mode = None

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode)
thread = None
thread_lock = Lock()

gCount = 0
gRooms = []
gUsers = []
gPasswords = []

#constants
ROOM_CAP = 2

## game variables
gameRooms =[]


def get_username(sid):
    global gUsers
    return next((x[1] for i, x in enumerate(gUsers) if x[0] == sid), None)

def get_roomIdx(room):
    global gRooms
    return next((i for i, x in enumerate(gRooms) if x["room"] == room), None)


def background_thread():
    """Example of how to send server generated events to clients."""
    while True:
        socketio.sleep(0.01)
        for i, v in enumerate(gameRooms):
            if v["game"].get_current_step() == "compare":
                socketio.emit('log_room', {'data': v["game"].compare()},to=v["room"])
                socketio.emit('game_score', {'score0': v["game"].players_scores[0], 'score1': v["game"].players_scores[1]},to=v["room"])
            elif v["game"].get_current_step() == "finish":
                socketio.emit('log_room', {'data': v["game"].finish()},to=v["room"])
                del v["game"]
                del gameRooms[i]
                print(gameRooms)
                socketio.emit('log_room', {'data': "Game finished."},to=v["room"])


       # socketio.emit('my_response',{'data': 'Server generated event'})


@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode)


@socketio.event
def echo(message):
    emit('my_response', {'data': message['data']})


@socketio.event
def my_broadcast_event(message):
    global gUsers
    sid = request.sid
    emit('emit_lobby',
         {'username': get_username(sid), 'data': message['data']},
         broadcast=True)


@socketio.event
def rooms_refresh():
    global gRooms
    print(str(gRooms))
    emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)


@socketio.event
def user_login(message):
    global gUsers
    username = message['username']
    sid = request.sid
    print('id: '+ sid + '/ username: '+username)
    sidIdx = next((i for i, x in enumerate(gUsers) if x[0] == sid), None)
    userIdx = next((i for i, x in enumerate(gUsers) if x[1] == username), None)
    if userIdx == None:
        if sidIdx == None:
            gUsers.append([sid,username])
            emit('my_response', {'data': 'Logged in as: '+username+'.'})
        else:
            gUsers[sidIdx] = [sid, username]
            print("Username changed to: "+ username)
            emit('my_response', {'data': 'Username changed to: '+username+'.'})
    else:
        print("Username is taken: " + username)
        emit('my_response', {'data': 'Username: '+username+' is already taken.'})

@socketio.on('create')
def create(data):
    global gRooms
    global gUsers
    global gPasswords

    room = data['room']
    password = data['password']
    set_password = data['set_password']
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        roomIdx = get_roomIdx(room)
        if roomIdx !=None:
            emit('my_response', {'data': room + ' already exists.'})
        else:
            join_room(room)
            print(room + ' has been created.')
            print(username + ' has entered the room: ' + room)
            emit('my_response', {'data': room + ' has been created. '+username + ' has entered the room: ' + room},
                 broadcast=True)
            emit('log_room', {'data': room + ' has been created. '+username + ' has entered the room.'},
                 to=room)
            gRooms.append({"room": room, "users": [username], "set_password": set_password})
            emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
            emit('update_room_name', {'room': room})
            gPasswords.append({"room": room, "password": password, "set_password": set_password})


@socketio.on('join')
def on_join(data):
    global gRooms
    global gUsers
    global gPasswords
    password_correct = False

    room = data['room']
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        roomIdx = get_roomIdx(room)
        if roomIdx !=None:
            usersInRoom = len(gRooms[roomIdx].get("users"))
            if  usersInRoom < ROOM_CAP:
                password = next((x["password"] for i, x in enumerate(gPasswords) if x["room"] == room), None)
                set_password = next((x["set_password"] for i, x in enumerate(gPasswords) if x["room"] == room), None)

                if set_password:
                    cb = call('request_password', {'room': room})
                    if cb == password:
                        password_correct = True
                        print("password_correct")
                    else:
                        emit('my_response', {'data': 'Password for room: '+room+' incorrect.'})

                print("password_correct "+str(password_correct))
                if not set_password or password_correct:
                    print("if not set_password or password_correct")
                    join_room(room)
                    print(username + ' has entered the room: ' + room)
                    emit('my_response', {'data': username + ' has entered the room: ' + room + '.'},
                         broadcast=True)
                    gRooms[roomIdx]["users"].append(username)
                    emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
                    emit('log_room', {'data': 'User ' + username + ' has entered the room.'},
                         to=room)
                    emit('update_room_name', {'room': room})
            else:
                print(username + ' cannot enter the room: ' + room + '. Users in the room: ' +str(usersInRoom)+'/'+str(ROOM_CAP))
                emit('my_response', {'data': 'You cannot enter the room: ' + room + '. Users in the room: ' +str(usersInRoom)+'/'+str(ROOM_CAP)})
        else:
            emit('my_response', {'data': 'Room: '+ room + ' does not exit.'})


@socketio.event
def leave():
    global gRooms
    global gUsers
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
        leave_room(room)
        roomIdx = get_roomIdx(room)
        gRooms[roomIdx]["users"].remove(username)
        emit('log_room', {'data': 'User ' + username+' has left the room.'},
             to=room)
        emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
        emit('update_room_name', {'room': 'None'})


@socketio.on('close_room')
def on_close_room():
    global gRooms
    global gUsers
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in." })
    else:
        room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
        emit('my_response', {'data': 'Room ' + room + ' is closing.'},
             to=room)
        emit('log_room', {'data': 'Room ' + room + ' is closing.'},
             to=room)
        close_room(room)
        roomIdx = get_roomIdx(room)
        del gRooms[roomIdx]
        emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
        passwordIdx = next((i for i, x in enumerate(gPasswords) if x["room"] == room), None)
        del gPasswords[passwordIdx]
        print(gPasswords)


@socketio.event
def outside_room_event(message):
    global gUsers
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        emit('emit_room',
             {'username':username,'data': message['data']},
                to=message['room'])

@socketio.event
def room_post(message):
    global gUsers
    global gRooms
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
        emit('emit_room',
             {'username':username,'data': message['data']},
                to=room)


@socketio.event
def disconnect_request():
    @copy_current_request_context
    def can_disconnect():
        disconnect()
    # for this emit we use a callback function
    # when the callback function is invoked we know that the message has been
    # received and it is safe to disconnect
    emit('my_response',
         {'data': 'Disconnected!'}, callback=can_disconnect)


@socketio.event
def my_ping():
    emit('my_pong')


@socketio.event
def connect():
    global thread
    global gCount
    with thread_lock:
        if thread is None:
            thread = socketio.start_background_task(background_thread)
    gCount += 1
    print('Client Connected  ' + str(gCount))
    emit('my_response', {'data': 'Connected'})
    emit('status', {'count': gCount}, broadcast=True)


@socketio.on('disconnect')
def test_disconnect():
    global gCount
    global gUsers
    sid = request.sid
    userIdx = next((i for i, x in enumerate(gUsers) if x[0] == sid), None)
    if userIdx!=None:
        del gUsers[userIdx]
        print('User removed. Users list: '+str(gUsers))
    print('Client disconnected', request.sid)
    gCount -= 1
    print("gCount: " + str(gCount))
    emit('status', {'count': gCount},broadcast=True)


######
@socketio.on('game_create')
def game_create():
    global gRooms
    global gUsers
    global gameRooms
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
        if room == None:
            emit('my_response', {'data': "You have to be in a room to create a game."})
        else:
            roomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
            players = gRooms[get_roomIdx(room)]["users"]
            print("players = " + str(len(players)))
            if roomIdx != None:
                emit('room_log', {'data': "Game already exists in this room."}, to=room)
                print("Game already exists in this room.")
                print(gameRooms)
            elif len(players) < 2:
                emit('log_room', {'data': "You need two players two create a game."}, to=room)
                print("You need two players two create a game.")
            else:
                game = Game(players)
                gameRooms.append({"room": room, "users": players, "game": game})
                emit('log_room', {'data': 'Game created.'},
                     to=room)

@socketio.on('game_update')
def game_update():
    global gRooms
    global gUsers
    global gameRooms
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
        if room == None:
            emit('my_response', {'data': "You have to be in a room to update a game."})
        else:
            roomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
            if roomIdx == None:
                emit('log_room', {'data': 'Game does not exist.'},
                     to=room)
            else:
                gameRooms[roomIdx]["game"].update()
                emit('log_room', {'data': 'Game updated.'},
                     to=room)
@socketio.on('game_throw')
def game_throw():
    global gRooms
    global gUsers
    global gameRooms
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
        if room == None:
            emit('my_response', {'data': "You have to be in a room to update a game."})
        else:
            roomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
            if roomIdx == None:
                emit('log_room', {'data': 'Game does not exist.'},
                     to=room)
            else:
                result = gameRooms[roomIdx]["game"].throw(username)
                emit('log_room', {'data': 'Throw '+username+': '+result},
                     to=room)

class Game(object):

    def __init__(self, players, width=600, height=400):
        self.x = 0
        self.steps = {"throw":[False,False,True],"compare":[False,False,False],"finish":[False,False,False]}
        self.players=players
        #self.thrown = [False,False]
        self.players_dice=[[0],[0]]
        self.players_scores=[0,0]
        print("init")

    def update(self):
        self.x += 1
        print("update; x=", self.x)

    def get_current_step(self):
        return next((key for key, value in self.steps.items() if value[2] == True), None)
    def throw(self, player):
        playerIdx=self.players.index(player)

        if not self.steps["throw"][playerIdx] and self.steps["throw"]:
            self.players_dice[playerIdx] = random.randrange(6)+1
            self.steps["throw"][playerIdx] = True

            if all(self.steps["throw"]):
                self.steps["compare"][2] = True
                self.steps["throw"][2] = False
            return str(self.players_dice[playerIdx])
        elif not self.steps["throw"]:
            return "Cannot throw."
        elif self.steps["throw"][playerIdx]:
            return "Player have already thrown."

    def compare(self):
        coms = [str(self.players[0]+" scores."), str(self.players[1]+" scores."), "Draw."]
        com=-1
        self.steps["compare"][2] = False
        self.steps["throw"] = [False,False,True]

        if self.players_dice[0] > self.players_dice[1]:
            self.players_scores[0] += 1
            print(self.players_scores)
            com=0

        elif self.players_dice[0] < self.players_dice[1]:
            self.players_scores[1] += 1
            print(self.players_scores)
            com=1

        else:
            print(self.players_scores)
            com=2
        self.steps["compare"][2] = False
        if self.players_scores[0]>=3:
            self.steps["finish"][2] = True
            return

        else:
            self.steps["throw"] = [False,False,True]
    def compare(self):
        coms = [str(self.players[0]+" scores."), str(self.players[1]+" scores."), "Draw."]
        com=-1
        self.steps["compare"][2] = False

        if self.players_dice[0] > self.players_dice[1]:
            self.players_scores[0] += 1
            print(self.players_scores)
            com=0

        elif self.players_dice[0] < self.players_dice[1]:
            self.players_scores[1] += 1
            print(self.players_scores)
            com=1

        else:
            print(self.players_scores)
            com=2
        self.steps["compare"][2] = False
        if self.players_scores[0]>=3 or self.players_scores[1]>=3:
            self.steps["finish"][2] = True
        else:
            self.steps["throw"] = [False,False,True]
        return coms[com]
    def finish(self):
        print("finish")
        if self.players_scores[0]>self.players_scores[1]:
            return str("Player " + self.players[0]+ " has won.")
        else:
            return str("Player " + self.players[1] + " has won.")


if __name__ == '__main__':
    socketio.run(app, debug=True)
