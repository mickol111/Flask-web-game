from threading import Lock
from flask import Flask, render_template, session, request, \
    copy_current_request_context
from flask_socketio import SocketIO, emit, join_room, leave_room, \
    close_room, call, disconnect,send
import random


async_mode = None
app = Flask(__name__)   # utworzenie obiektu Flask
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode=async_mode) # Utworzenie gniazda sieciowego i przypisanie go do utworzonego obiektu Flask
thread = None
thread_lock = Lock()

gCount = 0  # liczba połączonych klientów
gRooms = [] # tablica zawierająca dane dotyczące pokojów: nazwa pokoju, nazwy uzytkowników w pokoju oraz czy dla pokoju jest ustawione hasło
gUsers = [] # tablica zawierająca dane dotyczące użytkowników: ID sesji i nazwę użytkownika
gPasswords = [] # tablica zawierająca hasła do pokojów

#constants
ROOM_CAP = 2

## game variables
gameRooms =[]   # tablica zawierająca obiekty gry w poszczególnych pokojach i informacje o nich
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

### Funkcje służące do uzyskania informacji o nazwie użytkownika na podstawie jego ID, itp.
def get_sid(username):
    global gUsers
    return next((x[0] for i, x in enumerate(gUsers) if x[1] == username), None)

def get_username(sid):
    global gUsers
    return next((x[1] for i, x in enumerate(gUsers) if x[0] == sid), None)

def get_roomIdx(room):
    global gRooms
    return next((i for i, x in enumerate(gRooms) if x["room"] == room), None)


### Wątek działający w tle, w którym w pętli wykonywane są operacje związane z grą.
def background_thread():
    while True:
        socketio.sleep(0.01) # Pętla jest wykonywana co 0.01 sekundy.
        for i, v in enumerate(gameRooms): # Pętla iterująca to wszystkich utworzonych grach i sprawdzająca dla nich warunki.
            if v["game"].get_current_step() == "throw_send":
                users, hands = v["game"].get_hand()
                sid=[0,0]
                sid[0] = next((x[0] for i, x in enumerate(gUsers) if x[1] == users[0]), None)
                sid[1] = next((x[0] for i, x in enumerate(gUsers) if x[1] == users[1]), None)
                for j in range(2):
                    socketio.emit('game_dice', {'user': users[j],'d1':hands[j][0],'d2':hands[j][1],'d3':hands[j][2],'d4':hands[j][3], 'd5':hands[j][4]}, room = sid[j])
                    v["game"].throw_send()
                socketio.emit('log_room', {'data': "To rethrow, check dice and accept."}, to=v["room"]) # to=room - dane
                # wysłane do użytkowników znajdujących się w pokoju o podanym ID sesji połączenia.
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


@app.route('/') # wywoływane po wpisaniu adresu serwera w przeglądarce
def index(): # funkcja renderująca stronę HTML
    return render_template('index.html', async_mode=socketio.async_mode)


### Funkcje obsługujące zdarzenia związane z gniazdem sieciowym.
# Funkcje z dekoratorem @socketio.event wywoływane są po wyemitowaniu przez klienta danych z podaniem nazwy funkcji, np. 'echo'.
@socketio.event
def echo(message): # Funkcja zwraca wysłane przez klienta dane do tego klienta. Dane te są wydrukowane tylko u klienta, który je wysłał.
    emit('my_response', {'data': message['data']})


@socketio.event
def my_broadcast_event(message): # Funkcja realizująca broadcast do wszystkich połączonych aplikacji klienta, z podaniem nazwy użytkownika, który wysłał wiadomość.
    global gUsers
    sid = request.sid # odczytanie ID sesji połączenia
    emit('emit_lobby',
         {'username': get_username(sid), 'data': message['data']},
         broadcast=True) # broadcast=True - wiadomość emitowana do wszystkich klientów


@socketio.event
def rooms_refresh(): # Funkcja odświeżająca tablicę z pokojami i znajdującymi się w nich użytkownikami.
    global gRooms
    print(str(gRooms))
    emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)


@socketio.event
def user_login(message): # Funkcja wywoływana po wpisaniu nazwy użytkownika i naciśnięciu przycisku Login.
    # Jeżeli wprowadzona nazwa uzytkownika nie jest zajęta, do tablicy z użytkownikami dodawany jest nowy wpis, zawierający ID sesjji i nazwę użytkownika.
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


# @socketio.on('identyfikator') tworzy handler eventu po stronie serwera.
@socketio.on('create') # Funkcja jest wywoływana w odpowiedzi na socket.emit('create', ... po stronie klienta.
def create(data): # Funkcja wywoływana po wprowadzeniu przez użytkownika danych i naciśnięciu przycisku Create Room.
    # Jeżeli użytkownik jest zalogowany i pokój o tej nazwie nie istnieje, do tablicy gRooms dodawany jest
    # słownik zawierający nazwę pokoju, nabelę z nazwami użytkowników znajdujących się w danym pokoju oraz informację,
    # czy dostęp do pokoju zabezpieczony jest hasłem.
    # Do tablicy gPasswords dodawany jest słownik zawierający nazwę pokoju, hasło i informację, czy dostęp do pokoju zabezpieczony jest hasłem
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
            join_room(room) # Utworzenie pokoju i dołączenie do niego . join_room to funkcja z biblioteki Flask-SocketIO
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
def on_join(data): # Funkcja wywoływana po wprowadzeniu przez użytkownika nazwy pokoju i naciśnięciu przycisku Join Room.
    # Dołączenie użytkownika do wybranego pokoju, jeżeli warunki zostały spełnione i wpisanie go do tablicy gRooms.
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
                    cb = call('request_password', {'room': room}) # W ramach callbacku na żądanie 'request_password' serwera, klient wysyła hasło, wprowadzone w popupie.
                    if cb == password:
                        password_correct = True
                        print("password_correct")
                    else:
                        emit('my_response', {'data': 'Password for room: '+room+' incorrect.'})

                print("password_correct "+str(password_correct))
                if not set_password or password_correct:
                    print("if not set_password or password_correct")
                    join_room(room) # Dołączenie do pokoju.
                    print(username + ' has entered the room: ' + room)
                    emit('my_response', {'data': username + ' has entered the room: ' + room + '.'},
                         broadcast=True)
                    gRooms[roomIdx]["users"].append(username) # Dopisanie użytkownika do tablicy z użytkownikami w odpowiednim słowniku tablicy gRooms
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
def leave(): # Funkcja wywoływana po wprowadzeniu przez użytkownika nazwy pokoju i naciśnięciu przycisku Leave Room.
    # Powoduje wyjście użytkownika z pokoju i usunięcie go z wpisu dotyczącego danego pokoju w tablicy gRooms.
    global gRooms
    global gUsers
    sid = request.sid
    username = get_username(sid)
    if username == None:
        emit('my_response', {'data': "You have to log in."})
    else:
        room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
        leave_room(room) # Wyjście z pokoju
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
def on_close_room(): # Funkcja wywoływana po wprowadzeniu przez użytkownika nazwy pokoju i naciśnięciu przycisku Close Room.
    # Powoduje zamknięcie pokoju i usunięcie dotyczącego go słownika z tablicy gRooms.
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
        close_room(room)    # zamknięcie pokoju
        roomIdx = get_roomIdx(room)

        gameRoomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
        if gameRoomIdx != None:
            del gameRooms[gameRoomIdx]["game"] # usunięcie obiektu gry w danym pokoju
            del gameRooms[gameRoomIdx]  # usunięcie pozycji dostyczącej pokoju z tablicy gameRooms.
            socketio.emit('log_room', {'data': "Game closing."}, to = room)

        del gRooms[roomIdx] # usunięcie pozycji dotyczącej pokoju z gRooms
        emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)
        passwordIdx = next((i for i, x in enumerate(gPasswords) if x["room"] == room), None)
        del gPasswords[passwordIdx] # usunięcie pozycji dotyczącej pokoju z gPasswords
        print(gPasswords)


@socketio.event
def outside_room_event(message):    # Funkcja wywoływana po podaniu przez użytkownika nazwy pokoju, wprowadzeniu wiadomości i zatwierzeniu przyciskiem Send to Room.
    # Powoduje wysłanie wiadomości do podanego pokoju. Wiadomość pojawia się w logu pokoju.
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
def room_post(message): # Funkcja wywoływana po wprowadzeniu wiadomości i zatwierdzeniu przyciskiem Send.
    # Powoduje wysłanie wiadomości do pokoju, w którym użytkownik się znajduje
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
def disconnect_request():   # Funkcja wywoływana po naciśnięciu przycisku Disconnect.
    # Powoduje zakończenie połączenie klienta z serwerem.
    @copy_current_request_context
    def can_disconnect():
        disconnect()
    emit('my_response',
         {'data': 'Disconnected!'}, callback=can_disconnect) # wykorzystano funkcję callback. Gdy jest ona wywołana,
    # mamy pewność że wiadomość została dostarczona i można się bezpiecznie rozłączyć.


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


@socketio.on('disconnect') # Identyfikator disconnect jest nazwą zarezerwowaną. Zdarzenie ma miejsce, gdy następuje
# przerwanie połączenia klienta z serwerem (poprzez naciśnięcie przycisku disconnect lub zamknięcie karty przeglądarki).
def test_disconnect():
    global gCount
    global gUsers
    sid = request.sid
    userIdx = next((i for i, x in enumerate(gUsers) if x[0] == sid), None)
    username = get_username(sid)
    room = next((x["room"] for i, x in enumerate(gRooms) if username in x["users"]), None)
    if userIdx!=None:
        if room!= None:
            leave_room(room) # wyjście z pokoju
            roomIdx = get_roomIdx(room)

            gameRoomIdx = next((i for i, x in enumerate(gameRooms) if x["room"] == room), None)
            if gameRoomIdx != None:
                del gameRooms[gameRoomIdx]["game"]
                del gameRooms[gameRoomIdx]
                socketio.emit('log_room', {'data': "Game closing. User has disconnected"}, to=room)

            gRooms[roomIdx]["users"].remove(username) # usunięcie użytkownika z wpisu dotyczącego pokoju , w którym się znajdował z tablicy gRooms.
            emit('log_room', {'data': 'User ' + username+' has disconnected.'},
                 to=room)
            emit('rooms_status', {"rooms": str(gRooms)}, broadcast=True)
        del gUsers[userIdx] # usunięcie użytkownika z tablicy gUsers
        print('User removed. Users list: '+str(gUsers))
    print('Client disconnected', request.sid)
    gCount -= 1
    print("gCount: " + str(gCount))
    emit('status', {'count': gCount},broadcast=True)


###### Poniższe funkcje dotyczą zdarzeń związanych z grą.
@socketio.on('game_create') # Funkcja jest wywoływana po naciśnięciu przycisku Game Create.
# Utworzenie instancji gry dla danego pokoju.
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
                game = Game(players) # Utworzenie obiektu game podając nazwy obu użytkowników w danym pokoju
                gameRooms.append({"room": room, "users": players, "game": game}) # Dodanie do tablicy gameRooms słownika
                # zawierającego nazwę pokoju, tablicę z nazwami użytkowników w danym pokoju i instancję gry.
                emit('log_room', {'data': 'Game created.'},
                     to=room)
                socketio.emit('current_step', {'data': "Throw"}, to=room) # przejście do kroku gry Throw

@socketio.on('game_update') # Funkcja niewykorzystywana w finalnej wersji
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


@socketio.on('game_throw') # Funkcja jest wywoływana po naciśnięciu przycisku Throw.
# Wykonywany jest rzut kośćmi - metoda throw obiektu klasy Game.
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
                result = gameRooms[roomIdx]["game"].throw(username) #wykonanie rzutu dla gracza pozyskanie wyniku rzutu (tekst)
                other_player = gameRooms[roomIdx]["game"].get_other_players_id(username) # pozyskanie nazwy drugiego uczestnika gry
                player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(username) # pozyskanie wartości kości gracza
                other_player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(other_player) # pozyskanie kości przeciwnika
                emit('log_room', {'data': 'Throw '+username+': '+result},
                     to=room)
                try:
                    emit('users_dice', {'data1': player_dice, 'username1': username, 'data2': other_player_dice,
                                        'username2': other_player},
                         room=sid) # wysłanie wartości własnych kości do obu graczy w celu wyświetlenia
                    if gameRooms[roomIdx]["game"].get_step_player("throw",other_player):
                        emit('users_dice', {'data2': player_dice, 'username2': username, 'data1': other_player_dice,
                                            'username1': other_player},
                             room=get_sid(other_player))  # wysłanie wartości kości przeciwnika do obu graczy w celu wyświetlenia
                    else:
                        socketio.emit('current_step', {'data': "Waiting for the other player to throw"}, room=sid)

                except Exception as e:
                    print(e)

@socketio.on('game_rethrow') # Funkcja jest wywoływana po naciśnięciu przycisku Rethrow.
# Wykonywany jest przerzucenie kości - metoda rethrow obiektu klasy Game.
def game_rethrow(message):
    global gRooms
    global gUsers
    global gameRooms
    sid = request.sid
    username = get_username(sid)
    rethrowIds = [message['d1'],message['d2'],message['d3'],message['d4'],message['d5']] # lista zawierająca informację,
    # czy kość oznaczono jako do przerzucenia

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
                    result = gameRooms[roomIdx]["game"].rethrow(username,rethrowIds) #wykonanie przerzucenia dla gracza i pozyskanie wyniku (tekst)
                    emit('log_room', {'data': 'Rethrow ' + username + ': ' + result},
                         to=room)
                    other_player = gameRooms[roomIdx]["game"].get_other_players_id(username) # pozyskanie nazwy drugiego uczestnika gry
                    player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(username) # pozyskanie wartości kości gracza
                    other_player_dice = gameRooms[roomIdx]["game"].get_hand_by_username(other_player) # pozyskanie kości przeciwnika
                    try:
                        emit('users_dice', {'data1': player_dice, 'username1': username, 'data2': other_player_dice,
                                            'username2': other_player},
                             room=sid)  # wysłanie wartości własnych kości do obu graczy w celu wyświetlenia
                        if gameRooms[roomIdx]["game"].get_step_player("rethrow", other_player):
                            emit('users_dice', {'data2': player_dice, 'username2': username, 'data1': other_player_dice,
                                                'username1': other_player},
                                 room=get_sid(other_player)) # wysłanie wartości kości przeciwnika do obu graczy w celu wyświetlenia
                        else:
                            socketio.emit('current_step', {'data': "Waiting for the other player to rethrow"}, room=sid)

                    except Exception as e:
                        print(e)
                else:
                    emit('log_room', {'data': 'Cannot rethrow.'},
                         to=room)


### Kolejna sekcja zawiera deklarację klasy Game oraz funkcję wykorzystywaną w jej metodach
class Game(object): # Klasa gry. Silnik gry.
    def __init__(self, players): # Argumentem konstruktora jest lista nazw użytkowników obu graczy.
        # Aktualny krok gry
        self.steps = {"throw":[False,False,True],"throw_send":[False,False,False],"rethrow":[False,False,False],"compare":[False,False,False],"finish":[False,False,False]}
        self.players = players
        self.hands = [] # lista zawierająca strukturę identyfikującą rękę (układ kości) dla każdego z graczy
        self.players_dice=[[0],[0]] # kości obu graczy
        self.players_scores=[0,0] # wynik rozgrywki
        print("game init")

    def get_current_step(self): # metoda zwracająca aktualny krok gry
        return next((key for key, value in self.steps.items() if value[2] == True), None)

    def get_step_player(self,step,player): # metoda zwracająca status określonego kroku dla gracza
        playerIdx = self.players.index(player)
        return self.steps[step][playerIdx]

    def get_hand(self): # metoda zwracająca listę z nazwami użytkoników graczy i listę z kości graczy
        return self.players, self.players_dice

    def get_hand_by_username(self,player): # metoda zwracająca kości podanego gracza
        playerIdx = self.players.index(player)
        return self.players_dice[playerIdx]

    def get_other_players_id(self,player): # metoda zwracająca kości przeciwnika podanego gracza
        for i in self.players:
            if i != player:
                return i
        return None

    def throw(self, player): # metoda realizująca rzut dla gracza
        playerIdx=self.players.index(player)
        if not self.steps["throw"][playerIdx] and self.steps["throw"]:
            vals =[random.randrange(6)+1 for i in range(5)] # losowanie wartości kości
            vals.sort(reverse=True)
            self.players_dice[playerIdx] = vals
            self.steps["throw"][playerIdx] = True

            if all(self.steps["throw"]): # Jeżeli obaj gracze wykonali rzut, następuje przejście do następnego kroku.
                self.steps["throw_send"][2] = True
                self.steps["throw"][2] = False
            self.hands = [identify_hand(self.players_dice[0]), identify_hand(self.players_dice[1])] # identyfikacja układów, jakie posiadają gracze
            return str(self.players_dice[playerIdx])
        elif not self.steps["throw"]:
            return "Cannot throw."
        elif self.steps["throw"][playerIdx]:
            return "Player have already thrown dice."

    def throw_send(self): # metoda przełączająca krok gra z rethrow_send na rethrow
        self.steps["rethrow"][2] = True
        self.steps["throw_send"][2] = False
        self.steps["rethrow"] = [False, False, True]

    def rethrow(self, player, rethrowIds): # metoda realizująca przerzucenie kości dla gracza; argumentem jest informacja, które kości są do przerzucenia
        playerIdx = self.players.index(player)
        if not self.steps["rethrow"][playerIdx] and self.steps["rethrow"]:
            vals = self.players_dice[playerIdx].copy()
            for i, v in enumerate(rethrowIds): # losowanie nowych wartości dla kości oznaczonych do przerzucenia
                if v == 1:
                    vals[i] = random.randrange(6)+1
            vals.sort(reverse=True)
            self.players_dice[playerIdx] = vals
            self.steps["rethrow"][playerIdx] = True
            if all(self.steps["rethrow"]): # Jeżeli obaj gracze wykonali przerzucenie, następuje przejście do następnego kroku.
                self.steps["compare"][2] = True
                self.steps["rethrow"][2] = False

            self.hands = [identify_hand(self.players_dice[0]), identify_hand(self.players_dice[1])] # identyfikacja układów, jakie posiadają gracze
            return str(self.players_dice[playerIdx])
        elif not self.steps["rethrow"]:
            return "Cannot rethrow."
        elif self.steps["rethrow"][playerIdx]:
            return "Player have already rethrown dice."

    def compare(self): # metoda realizująca porównanie układów, które posiadają gracze i określająca, kto wygrywa rundę
        coms = [str(self.players[0]+" scores."), str(self.players[1]+" scores."), "Draw."]
        com=-1

        com = compare_hands(self.hands, self.players_scores, com) # porównanie układów

        self.steps["compare"][2] = False
        if self.players_scores[0]>=3 or self.players_scores[1]>=3: # Jeżeli któryś z graczy zdobył trzy lub więcej punktów,
            # przejście do kroku finish.
            self.steps["finish"][2] = True
        else: # W przeciwnym przypadku przejście do kroku throw
            self.steps["throw"] = [False, False, False]
            self.steps["throw"] = [False,False,True]
        return coms[com]

    def finish(self): # Zakończenie gry i wystawienie komunikatu, który gracz wygrał.
        print("finish game")
        if self.players_scores[0] > self.players_scores[1]:
            return str("Player " + self.players[0]+ " has won.")
        else:
            return str("Player " + self.players[1] + " has won.")


# Funkcje wykorzystywane w klasie Game
def find_max_len(lst): # Wyszukuje warość, która najczęściej pojawiła się na kościach.
    # Zwraca liczbę wystąpień najczęstszej wartości, ostatnią pozycję kości o najczęstszej wartości i najczęscszą wartość.
    if len(lst) != 0:
        maxIdx = max((len(l), i, l[0]) for i, l in enumerate(lst))
        return maxIdx[0], maxIdx[1], maxIdx[2]
    else:
        return -1, -1, -1


def all_max_len(lst): # wyszukuje wszystkie najczęstsze wartości kości
    # (1 i 2 kości o tej samej wartości mogą wystąpić więcej niż raz)
    lstTemp = lst.copy() # Konieczne jest wykonanie kopii analizowanej listy z wartościami kości,
    # ponieważ wykonywane jest usuwanie jej elementów.
    maxLen = 0
    maxLenTemp = 0
    maxLenIdx = []
    idx = 0
    i = 0
    while True: # Najczęściej występujące wartości są identyfikowane, zapisywana jest ostatnia pozycja i liczba wystąpień,
        # a następnie wartości te są usuwane z listy i operacja jest powtarzana, aż liczba wystąpień najczęstszej wartości
        # będzie mniejsza od tej zapisanej wcześniej.
        maxLenTemp,idx, val = find_max_len(lstTemp)
        if maxLenTemp < maxLen:
            break
        else:
            maxLen = maxLenTemp
            maxLenIdx.append(idx)
            del lstTemp[idx]
            i += 1
    return [maxLenIdx, maxLen]


def identify_hand(dice): # identyfikacja układu kości
    # Funkcja zwraca wartość odpowiadającą układowi kości, wartości tego układu oraz największą wartość poza układem.
    hand = 0 # wartości zmiennej korespondują z układami zapisanymi w słowniku HANDS
    hand_values = []
    max_other_value = 0

    values = set(dice) # unikatowe wartości kości
    newlist = [[y for y in dice if y == x] for x in values] # zapisanie jednakowych wartości w jednej liście
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

def compare_hands(hands, players_scores, com): # porównanie układów obu graczy
    if hands[0]["hand"] > hands[1]["hand"]:
        com = 0
    elif hands[0]["hand"] < hands[1]["hand"]:
        com = 1
    else: # Jeżeli układy są takie same, porównywane są wartości układów.
        if hands[0]["hand_values"][0] > hands[1]["hand_values"][0]:
            com = 0
        elif hands[0]["hand_values"][0] < hands[1]["hand_values"][0]:
            com = 1
        else: # Jeżeli ukłądy i ich wartości są takie same, porównywane są największe wartości poza układem.
            if hands[0]["max_other_value"] > hands[1]["max_other_value"]:
                com = 0
            elif hands[0]["max_other_value"] < hands[1]["max_other_value"]:
                com = 1
            else:
                com = 2
    if com == 0: # Zwiększenie licznika gracza, który wygrał rundę.
        players_scores[0] += 1
    elif com == 1:
        players_scores[1] += 1
    return com

if __name__ == '__main__':
    socketio.run(app, debug=True)
