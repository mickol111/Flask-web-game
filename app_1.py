from threading import Lock
from flask import Flask, render_template, session, request, \
    copy_current_request_context
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, call, disconnect,send

import random

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
HANDS = {
    "high card": 0,
    "one pair": 1,
    "two pairs": 2,
    "three of a kind": 3,
    "straight": 4,
    "full house": 5,
    "four of a kind": 6,
    "five of a kind": 7
}

def get_sid(username):
    global gUsers
    return next((x[0] for i, x in enumerate(gUsers) if x[1] == username), None)

def get_username(sid):
    global gUsers
    return next((x[1] for i, x in enumerate(gUsers) if x[0] == sid), None)

def get_roomIdx(room):
    global gRooms
    return next((i for i, x in enumerate(gRooms) if x["room"] == room), None)


def background_thread():
    while True:
        socketio.sleep(0.01)
        for i, v in enumerate(gameRooms):
            if v["game"].get_current_step() == "throw_send":
                users, hands = v["game"].get_hand()
                sid=[0,0]
                sid[0] = next((x[0] for i, x in enumerate(gUsers) if x[1] == users[0]), None)
                sid[1] = next((x[0] for i, x in enumerate(gUsers) if x[1] == users[1]), None)
                for j in range(2):
                    socketio.emit('game_dice', {'user': users[j],'d1':hands[j][0],'d2':hands[j][1],'d3':hands[j][2],'d4':hands[j][3], 'd5':hands[j][4]}, room = sid[j])
                    v["game"].throw_send()
                socketio.emit('log_room', {'data': "To rethrow, check dice and accept."}, to=v["room"])
                socketio.emit('current_step', {'data': "Rethrow"}, to=v["room"])
            elif v["game"].get_current_step() == "compare":
                socketio.emit('log_room', {'data': v["game"].compare()}, to=v["room"])
                socketio.emit('game_score', {'score0': v["game"].players_scores[0], 'score1': v["game"].players_scores[1]},to=v["room"])
                socketio.emit('log_room', {'data': "Throw again."}, to=v["room"])
                socketio.emit('current_step', {'data': "Throw"}, to=v["room"])
            elif v["game"].get_current_step() == "finish":
                socketio.emit('log_room', {'data': v["game"].finish()},to=v["room"])
                del v["game"]
                del gameRooms[i]
                socketio.emit('log_room', {'data': "Game finished."},to=v["room"])
                socketio.emit('current_step', {'data': "Game finished"}, to=v["room"])



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
    emit('rooms_status', {"rooms": gRooms}, broadcast=True)


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
            emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)
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
                    emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)
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

        gameRoomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
        if gameRoomIdx != None:
            del gameRooms[gameRoomIdx]["game"]
            del gameRooms[gameRoomIdx]
            socketio.emit('log_room', {'data': "Game closing. User left the room"}, to=room)

        gRooms[roomIdx]["users"].remove(username)
        emit('log_room', {'data': 'User ' + username+' has left the room.'},
             to=room)
        emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)
        emit('update_room_name', {'room': 'None'})


@socketio.on('close_room')
def on_close_room():
    global gRooms
    global gUsers
    global gameRooms
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

        gameRoomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
        if gameRoomIdx != None:
            del gameRooms[gameRoomIdx]["game"]
            del gameRooms[gameRoomIdx]
            socketio.emit('log_room', {'data': "Game closing."}, to = room)

        del gRooms[roomIdx]
        emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)
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
    username = get_username(sid)
    room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
    if userIdx!=None:
        if room!= None:
            leave_room(room)
            roomIdx = get_roomIdx(room)

            gameRoomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
            if gameRoomIdx != None:
                del gameRooms[gameRoomIdx]["game"]
                del gameRooms[gameRoomIdx]
                socketio.emit('log_room', {'data': "Game closing. User has disconnected"}, to=room)

            gRooms[roomIdx]["users"].remove(username)
            emit('log_room', {'data': 'User ' + username+' has disconnected.'},
                 to=room)
            emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)
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
                socketio.emit('current_step', {'data': "Throw"}, to=room)

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
                other_player = gameRooms[roomIdx]["game"].get_other_players_id(username)
                player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(username)
                other_player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(other_player)
                emit('log_room', {'data': 'Throw '+username+': '+result},
                     to=room)
                try:
                    emit('users_dice', {'data1': player_dice, 'username1': username, 'data2': other_player_dice,
                                        'username2': other_player},
                         room=sid)
                    if gameRooms[roomIdx]["game"].get_step_player("throw",other_player):
                        emit('users_dice', {'data2': player_dice, 'username2': username, 'data1': other_player_dice,
                                            'username1': other_player},
                             room=get_sid(other_player))
                    else:
                        socketio.emit('current_step', {'data': "Waiting for the other player to throw"}, room=sid)

                except Exception as e:
                    print(e)

@socketio.on('game_rethrow')
def game_rethrow(message):
    global gRooms
    global gUsers
    global gameRooms
    sid = request.sid
    username = get_username(sid)
    rethrowIds = [message['d1'],message['d2'],message['d3'],message['d4'],message['d5']]

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
                if gameRooms[roomIdx]["game"].get_current_step() == "rethrow":
                    result = gameRooms[roomIdx]["game"].rethrow(username,rethrowIds)
                    emit('log_room', {'data': 'Rethrow ' + username + ': ' + result},
                         to=room)
                    other_player = gameRooms[roomIdx]["game"].get_other_players_id(username)
                    player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(username)
                    other_player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(other_player)
                    try:
                        emit('users_dice', {'data1': player_dice, 'username1': username, 'data2': other_player_dice,
                                            'username2': other_player},
                             room=sid)
                        if gameRooms[roomIdx]["game"].get_step_player("rethrow", other_player):
                            emit('users_dice', {'data2': player_dice, 'username2': username, 'data1': other_player_dice,
                                                'username1': other_player},
                                 room=get_sid(other_player))
                        else:
                            socketio.emit('current_step', {'data': "Waiting for the other player to rethrow"}, room=sid)

                    except Exception as e:
                        print(e)
                else:
                    emit('log_room', {'data': 'Cannot rethrow.'},
                         to=room)
class Game(object):
    def __init__(self, players, width=600, height=400):
        self.x = 0
        self.steps = {"throw":[False,False,True],"throw_send":[False,False,False],"rethrow":[False,False,False],"compare":[False,False,False],"finish":[False,False,False]}
        self.players=players
        self.hands = []
        self.players_dice=[[0],[0]]
        self.players_scores=[0,0]
        print("init")

    def get_current_step(self):
        return next((key for key, value in self.steps.items() if value[2] == True), None)
    def get_step_player(self,step,player):
        playerIdx = self.players.index(player)
        return self.steps[step][playerIdx]
    def get_hand(self):
        return self.players, self.players_dice
    def get_hand_by_username(self,player):
        playerIdx = self.players.index(player)
        return self.players_dice[playerIdx]
    def get_other_players_id(self,player):
        for i in self.players:
            if i != player:
                return i
        return None
    def throw(self, player):
        playerIdx=self.players.index(player)
        if not self.steps["throw"][playerIdx] and self.steps["throw"]:
            vals =[random.randrange(6)+1 for i in range(5)]
            vals.sort(reverse=True)
            self.players_dice[playerIdx] = vals
            self.steps["throw"][playerIdx] = True

            if all(self.steps["throw"]):
                self.steps["throw_send"][2] = True
                self.steps["throw"][2] = False
            self.hands = [identify_hand(self.players_dice[0]), identify_hand(self.players_dice[1])]
            return str(self.players_dice[playerIdx])
        elif not self.steps["throw"]:
            return "Cannot throw."
        elif self.steps["throw"][playerIdx]:
            return "Player have already thrown dice."

    def throw_send(self):
        self.steps["rethrow"][2] = True
        self.steps["throw_send"][2] = False
        self.steps["rethrow"] = [False, False, True]


    def rethrow(self,player,rethrowIds):
        playerIdx=self.players.index(player)
        if not self.steps["rethrow"][playerIdx] and self.steps["rethrow"]:
            vals = self.players_dice[playerIdx].copy()
            for i,v in enumerate(rethrowIds):
                if v == 1:
                    vals[i] = random.randrange(6)+1
            vals.sort(reverse=True)
            self.players_dice[playerIdx] = vals
            self.steps["rethrow"][playerIdx] = True
            if all(self.steps["rethrow"]):
                self.steps["compare"][2] = True
                self.steps["rethrow"][2] = False

            self.hands = [identify_hand(self.players_dice[0]), identify_hand(self.players_dice[1])]
            return str(self.players_dice[playerIdx])
        elif not self.steps["rethrow"]:
            return "Cannot rethrow."
        elif self.steps["rethrow"][playerIdx]:
            return "Player have already rethrown dice."

    def compare(self):
        coms = [str(self.players[0]+" scores."), str(self.players[1]+" scores."), "Draw."]
        com=-1

        com = compare_hands(self.hands, self.players_scores, com)

        self.steps["compare"][2] = False
        if self.players_scores[0]>=3 or self.players_scores[1]>=3:
            self.steps["finish"][2] = True
        else:
            self.steps["throw"] = [False, False, False]
            self.steps["throw"] = [False,False,True]
        return coms[com]
    def finish(self):
        print("finish game")
        if self.players_scores[0]>self.players_scores[1]:
            return str("Player " + self.players[0]+ " has won.")
        else:
            return str("Player " + self.players[1] + " has won.")


def find_max_len(lst):
    #maxList = max(lst, key=lambda i: len(i))
    if len(lst) != 0:
        maxIdx = max((len(l), i, l[0]) for i, l in enumerate(lst))
        #maxLength = len(maxList)
        return maxIdx[0], maxIdx[1], maxIdx[2]
    else:
        return -1, -1, -1

def all_max_len(lst):
    lstTemp=lst.copy()
    maxLen = 0
    maxLenTemp=0
    maxLenIdx = []
    idx = 0
    i=0
    while True:
        maxLenTemp,idx, val = find_max_len(lstTemp)
        if maxLenTemp < maxLen:
            break
        else:
            maxLen = maxLenTemp
            maxLenIdx.append(idx)
            del lstTemp[idx]
            i += 1
    return [maxLenIdx, maxLen]


def identify_hand(dice):
    hand = 0
    hand_values = []
    max_other_value = 0

    values = set(dice)
    newlist = [[y for y in dice if y == x] for x in values]
    newlist_mov = newlist.copy()
    if all_max_len(newlist)[1] == 5:
        hand = 7
        hand_values = [newlist[all_max_len(newlist)[0][0]][0]]
    elif all_max_len(newlist)[1] == 4:
        hand = 6
        hand_values = [newlist[all_max_len(newlist)[0][0]][0]]
        del newlist_mov[all_max_len(newlist)[0][0]]
        max_other_value = find_max_len(newlist_mov)[2]
    elif all_max_len(newlist)[1] == 3:
        max_value = newlist[all_max_len(newlist)[0][0]][0]
        del newlist_mov[all_max_len(newlist)[0][0]]
        max_other_value = find_max_len(newlist_mov)
        if max_other_value[0] == 2:
            hand = 5
            hand_values = [max_value, max_other_value[2]]
            max_other_value = 0
        else:
            hand = 3
            hand_values = [max_value]
    elif all_max_len(newlist)[1] == 2:
        max_value = newlist[all_max_len(newlist)[0][0]][0]
        del newlist_mov[all_max_len(newlist)[0][0]]
        max_other_value = find_max_len(newlist_mov)
        if len(all_max_len(newlist)[0])>1:
            hand = 2
            hand_values = [max_value, max_other_value[2]]
            del newlist_mov[all_max_len(newlist_mov)[0][0]]
            max_other_value = find_max_len(newlist_mov)[2]
        else:
            hand = 1
            hand_values = [max_value]
            max_other_value = max_other_value[2]
    elif all_max_len(newlist)[1] == 1:
        if sorted(newlist) == sorted([[2],[3],[4],[5],[6]]):
            hand = 4
            hand_values = [6]
        elif sorted(newlist) == sorted([[1],[2],[3],[4],[5]]):
            hand = 4
            hand_values = [5]
        else:
            hand = 0
            hand_values = [newlist[all_max_len(newlist)[0][0]][0]]
            del newlist_mov[all_max_len(newlist_mov)[0][0]]
            max_other_value = find_max_len(newlist_mov)[2]

    return {"hand": hand, "hand_values": hand_values, "max_other_value": max_other_value}

def compare_hands(hands, players_scores, com):
    if hands[0]["hand"] > hands[1]["hand"]:
        com = 0
    elif hands[0]["hand"] < hands[1]["hand"]:
        com = 1
    else:
        if hands[0]["hand_values"][0] > hands[1]["hand_values"][0]:
            com = 0
        elif hands[0]["hand_values"][0] < hands[1]["hand_values"][0]:
            com = 1
        else:
            if hands[0]["max_other_value"] > hands[1]["max_other_value"]:
                com = 0
            elif hands[0]["max_other_value"] < hands[1]["max_other_value"]:
                com = 1
            else:
                com = 2
    if com == 0:
        players_scores[0] += 1
    elif com == 1:
        players_scores[1] += 1
    return com

if __name__ == '__main__':
    socketio.run(app, debug=True)
