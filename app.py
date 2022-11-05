from threading import Lock
from flask import Flask, render_template, session, request, \
    copy_current_request_context
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, rooms, disconnect,send

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

#constants
ROOM_CAP = 2

def get_username(sid):
    global gUsers
    return next((x[1] for i, x in enumerate(gUsers) if x[0] == sid), None)

def get_roomIdx(room):
    global gRooms
    return next((i for i, x in enumerate(gRooms) if x["room"] == room), None)


def background_thread():
    """Example of how to send server generated events to clients."""
    count = 0
    while True:
        socketio.sleep(10)
        count += 1
        socketio.emit('my_response',
                      {'data': 'Server generated event', 'count': count})


@app.route('/')
def index():
    return render_template('index.html', async_mode=socketio.async_mode)


@socketio.event
def my_event(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': message['data'], 'count': session['receive_count']})


@socketio.event
def my_broadcast_event(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': message['data'], 'count': session['receive_count']},
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
    userIdx = next((i for i, x in enumerate(gUsers) if x[0] == sid), None)
    session['receive_count'] = session.get('receive_count', 0) + 1
    if userIdx == None:
        gUsers.append([sid,username])
        emit('my_response', {'data': 'Logged in as: '+username+'.',
                             'count': session['receive_count']})
    else:
        gUsers[userIdx] = [sid, username]
        print("Username changed to: "+ username)
        emit('my_response', {'data': 'Username changed to: '+username+'.',
                             'count': session['receive_count']})


#@socketio.event
#def join(message):
#    join_room(message['room'])
#    session['receive_count'] = session.get('receive_count', 0) + 1
#    emit('my_response',
#         {'data': 'In rooms: ' + ', '.join(rooms()),
#          'count': session['receive_count']})


@socketio.on('join')
def on_join(data):
    global gRooms
    global gUsers
    room = data['room']
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in." ,
                             'count': session['receive_count']})
    else:
        roomIdx = get_roomIdx(room)
        if roomIdx !=None:
            usersInRoom = len(gRooms[roomIdx].get("users"))
            if  usersInRoom < ROOM_CAP:
                join_room(room)
                session['receive_count'] = session.get('receive_count', 0) + 1
                print(username + ' has entered the room: ' + room)
                emit('my_response', {'data': username + ' has entered the room.',
                                     'count': session['receive_count']},
                     broadcast=True)
                gRooms[roomIdx]["users"].append(username)
                emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
                emit('log_room', {'data': 'User ' + username + ' has entered the room.'},
                     to=room)
                emit('update_room_name', {'room': room})
            else:
                session['receive_count'] = session.get('receive_count', 0) + 1
                print(username + ' cannot enter the room: ' + room + '. Users in the room: ' +str(usersInRoom)+'/'+str(ROOM_CAP))
                emit('my_response', {'data': username + ' cannot enter the room: ' + room + '. Users in the room: ' +str(usersInRoom)+'/'+str(ROOM_CAP),
                                     'count': session['receive_count']})
        else:
            join_room(room)
            session['receive_count'] = session.get('receive_count', 0) + 1
            print(room + ' has been created.')
            print(username + ' has entered the room: ' + room)
            emit('my_response', {'data': room + ' has been created. '+username + ' has entered the room: ' + room,
                                 'count': session['receive_count']}, broadcast=True)
            emit('log_room', {'data': room + ' has been created. '+username + ' has entered the room.'},
                 to=room)
            gRooms.append({"room": room, "users": [username]})
            emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
            emit('update_room_name', {'room': room})

        join_room(room)
        session['receive_count'] = session.get('receive_count', 0) + 1
        print(username + ' has entered the room: ' + room)
        emit('my_response', {'data': username + ' has entered the room.',
                             'count': session['receive_count']},
             to=room)


@socketio.event
def leave(message):
    global gRooms
    global gUsers
    room = message['room']
    leave_room(room)
    sid = request.sid
    username = get_username(sid)
    roomIdx = get_roomIdx(room)
    if username != None:
        gRooms[roomIdx]["users"].remove(username)
        emit('log_room', {'data': 'User ' + username+' has left the room.'},
             to=room)
        emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
        emit('update_room_name', {'room': 'None'})


@socketio.on('close_room')
def on_close_room(message):
    global gRooms
    room=message['room']
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response', {'data': 'Room ' + room + ' is closing.',
                         'count': session['receive_count']},
         to=room)
    emit('log_room', {'data': 'Room ' + room + ' is closing.'},
         to=room)
    close_room(message['room'])
    roomIdx = get_roomIdx(room)
    del gRooms[roomIdx]
    emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)


@socketio.event
def outside_room_event(message):
    global gUsers
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in." ,
                             'count': session['receive_count']})
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
        emit('my_response', {'data': "You have to log in." ,
                             'count': session['receive_count']})
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
    session['receive_count'] = session.get('receive_count', 0) + 1
    # for this emit we use a callback function
    # when the callback function is invoked we know that the message has been
    # received and it is safe to disconnect
    emit('my_response',
         {'data': 'Disconnected!', 'count': session['receive_count']},
         callback=can_disconnect)


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
    emit('my_response', {'data': 'Connected', 'count': 0})
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


if __name__ == '__main__':
    socketio.run(app, debug=True)