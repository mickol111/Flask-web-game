from threading import Lock
from flask import Flask, render_template, session, request, \
    copy_current_request_context
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, call, disconnect,send

import keyboard

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

def get_username(sid):
    global gUsers
    return next((x[1] for i, x in enumerate(gUsers) if x[0] == sid), None)

def get_roomIdx(room):
    global gRooms
    return next((i for i, x in enumerate(gRooms) if x["room"] == room), None)


def background_thread():
    """Example of how to send server generated events to clients."""

    while True:
        game = PongGame(600, 400)
        game.run()
        socketio.sleep(10)



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


####PONG
class PongGame(object):

    def __init__(self, width, height):
        print("init")


        #self.board = Board(width, height)
        # zegar którego użyjemy do kontrolowania szybkości rysowania
        # kolejnych klatek gry
        #self.fps_clock = pygame.time.Clock()
        self.ball = Ball(width=20, height=20, x=width/2, y=height/2)
        self.player1 = Racket(width=80, height=20, x=width/2, y=height/2)


    def run(self):
        """
        Główna pętla programu
        """

        while not self.handle_events():
            # działaj w pętli do momentu otrzymania sygnału do wyjścia
            #self.ball.move(self.board, self.player1)
            print("run")
            #self.fps_clock.tick(30)
    def handle_events(self):
        """
        Obsługa zdarzeń systemowych, tutaj zinterpretujemy np. ruchy myszką

        :return True jeżeli pygame przekazał zdarzenie wyjścia z gry
        """

        """
        for event in pygame.event.get():
            if event.type == pygame.locals.QUIT:
                pygame.quit()
                return True

            if event.type == pygame.locals.MOUSEMOTION:
                # myszka steruje ruchem pierwszego gracza
                x, y = event.pos
                self.player1.move(x)
        """
        if keyboard.is_pressed('r'):
            print("R")
            socketio.emit('my_response',
                          {'data': 'Server generated event'})
            return True

class Drawable(object):
    """
    Klasa bazowa dla rysowanych obiektów
    """

    def __init__(self, width, height, x, y):
        self.width = width
        self.height = height
        self.x = x
        self.y=y

    def colliderect(self, Drawable):
        if self.x
class Ball():
    """
    Piłeczka, sama kontroluje swoją prędkość i kierunek poruszania się.
    """
    def __init__(self, width, height, x, y, x_speed=3, y_speed=3):
        self.width=width
        self.height=height
        self.x_speed = x_speed
        self.y_speed = y_speed
        self.start_x = x
        self.start_y = y
        self.x=x
        self.y=y

    def bounce_y(self):
        """
        Odwraca wektor prędkości w osi Y
        """
        self.y_speed *= -1

    def bounce_x(self):
        """
        Odwraca wektor prędkości w osi X
        """
        self.x_speed *= -1

    def reset(self):
        """
        Ustawia piłeczkę w położeniu początkowym i odwraca wektor prędkości w osi Y
        """
        self.move(self.start_x, self.start_y)
        self.bounce_y()

    def move(self, board, *args):
        """
        Przesuwa piłeczkę o wektor prędkości
        """
        self.x += self.x_speed
        self.y += self.y_speed

        if self.y < 0 or self.y > self.height:
            self.bounce_x()

        if self.x < 0 or self.x > self.width:
            self.bounce_y()

        for racket in args:
            if self.colliderect(racket):
                self.bounce_y()
class Racket():
    """
    Rakietka, porusza się w osi X z ograniczeniem prędkości.
    """

    def __init__(self, width, height, x, y, max_speed=10):
        super(Racket, self).__init__(width, height, x, y)
        self.y=height/2
        self.x=width/2
        self.max_speed = max_speed


    def move(self, y):
        """
        Przesuwa rakietkę w wyznaczone miejsce.
        """

        self.y += y



####
if __name__ == '__main__':
    game = PongGame(600, 400)
    socketio.run(app, debug=True)


####PONG

####