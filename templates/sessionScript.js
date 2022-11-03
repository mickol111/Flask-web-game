$(document).ready(function(){
      var socket = io.connect('http://' + document.domain + ':' + location.port);

            $('input.sync').on('input', function(event) {
      socket.emit('Slider value changed', {
        who:$(this).attr('id'),
        data: $(this).val()
     });
     return false;
      });

           socket.on('update value', function(msg) {
               console.log('Slider value updated');
               $('#' + msg.who).val(msg.data);
           });




      socket.on( 'connect', function() {
        socket.emit( 'my event', {
          data: 'User Connected'
        } )
        var form = $( 'form[name="chatForm"]' ).on( 'submit', function( e ) {
          e.preventDefault()
          let user_name = $( 'input.username' ).val()
          let user_input = $( 'input.message' ).val()
          socket.emit( 'my event', {
            user_name : user_name,
            message : user_input
          } )
          $( 'input.message' ).val( '' ).focus()
        } )
        var diceForm = $( 'form[name="diceForm"]' ).on( 'submit', function( e ) {
          e.preventDefault()
          let num = $( 'input.num' ).val()
          socket.emit( 'my event', {
            number : num
          } )
        } )
      } )
      socket.on( 'my response', function( msg ) {
        console.log( msg )
        if( typeof msg.user_name !== 'undefined' ) {
          $( 'h3' ).remove()
          $( 'div.message_holder' ).append( '<div><b style="color: #000">'+msg.user_name+'</b> '+msg.message+'</div>' )
        }
      })
      });