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
    username = next((x[1] for i, x in enumerate(gUsers) if x[0] == sid), None)
    if username == None:
        emit('my_response', {'data': "You have to log in." ,
                             'count': session['receive_count']})
    else:
        roomIdx = next((i for i, x in enumerate(gRooms) if x["room"] == room), None)
        if roomIdx !=None:
            usersInRoom = len(gRooms[roomIdx].get("users"))
            if  usersInRoom < ROOM_CAP:
                join_room(room)
                session['receive_count'] = session.get('receive_count', 0) + 1
                print(username + ' has entered the room: ' + room)
                emit('my_response', {'data': username + ' has entered the room.',
                                     'count': session['receive_count']},
                     to=room)
                gRooms[roomIdx]["users"].append(username)
                emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)
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
                                 'count': session['receive_count']})
            emit('my_response', {'data': room + ' has been created. '+username + ' has entered the room: ' + room,
                                 'count': session['receive_count']},
                 to=room)
            gRooms.append({"room": room, "users": [username]})
            emit('rooms_status', {'rooms': str(gRooms)}, broadcast=True)

        join_room(room)
        session['receive_count'] = session.get('receive_count', 0) + 1
        print(username + ' has entered the room: ' + room)
        emit('my_response', {'data': username + ' has entered the room.',
                             'count': session['receive_count']},
             to=room)


@socketio.event
def leave(message):
    leave_room(message['room'])
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': 'In rooms: ' + ', '.join(rooms()),
          'count': session['receive_count']})


@socketio.on('close_room')
def on_close_room(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response', {'data': 'Room ' + message['room'] + ' is closing.',
                         'count': session['receive_count']},
         to=message['room'])
    close_room(message['room'])


@socketio.event
def my_room_event(message):
    session['receive_count'] = session.get('receive_count', 0) + 1
    emit('my_response',
         {'data': message['data'], 'count': session['receive_count']},
         to=message['room'])


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