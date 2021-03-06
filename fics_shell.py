#!/usr/bin/python
# -*- coding: utf-8 -*-

# TODO: after implementing and polishing move to scripts

"""
Interactive FICS console intended for mekk.fics learning and testing.

Connects to FICS, allows the user to issue commands, but shows all
command results, and all FICS-initiated notifications, in the form
returned by mekk.fics parsers (as appropriate python structures).

Additionally, all items which are not properly parsed are logged
to special files: not-parsed-notifications.txt and not-parsed-replies.txt,
so one can use console to grab example data for mekk.fics parser development.

Note: it doesn't work on Windows (due to problems with console
support), check http://twistedmatrix.com/trac/ticket/2157 for possible
patch.
"""
import pprint
import sys
import random
import time

from twisted.internet import stdio, reactor, defer
from twisted.protocols import basic
from mekk.fics import fics_connector, fics_client
from mekk.fics.datatypes import UnknownReply
import chess
import chessnet

import logging

#################################################################################
# Configuration
#################################################################################

from mekk.fics import FICS_HOST, FICS_PORT

#FICS_HOST='localhost' # proxy

FICS_USER='GuestCNBOT'
FICS_PASSWORD=''

# TODO
FINGER_TEXT="""mekk.fics example code: interactive_shell.py.
See http://bitbucket.org/Mekk/mekk.fics/ for more information."""

NOT_PARSED_NOTIFICATIONS_FILE="not-parsed-notifications.txt"
NOT_PARSED_REPLIES_FILE="not-parsed-replies.txt"

#################################################################################
# Actual client/bot code
#################################################################################

class MyFicsClient(fics_client.FicsClient):

    def __init__(self, console, model):
        super(MyFicsClient, self).__init__(label="My connection")
        self.interface_variables_to_set_after_login = [
            ]
        self.variables_to_set_after_login = {
            #'seek': '10 15'
            'open': 1
        }
        self.console = console
        self.model = model

    @defer.inlineCallbacks
    def on_login(self, user):
        yield self.set_finger(FINGER_TEXT)
        self.console.register_fics_client(self, user)

    def on_logout(self):
        if reactor.running:
            reactor.stop()

    @defer.inlineCallbacks
    def on_fics_information(self, what, args):
        if what == 'game_move':
            board = chess.Board(args.style12.fen)
            yield self.move(board)

        yield self.console.show_information(what, args)

    @defer.inlineCallbacks
    def move(self, board):
        try:
            selected, info = self.model.select_move(board, 4)
            print(board)
            print(selected)
            print(info)
            result = yield self.run_command(str(selected))

            self.tell_to(self.opponent_name, str(info))
#            for score, move in analysis[:5]:
#                move_str = '{} {:.2f}'.format(board.san(move), score)
#                print(move_str)
#                self.tell_to(self.opponent_name, move_str)

        except:
            pass


    @defer.inlineCallbacks
    def on_fics_unknown(self, what):
        if what.startswith("Challenge:"):
            print "I accept your challenge!!!"
            result = yield self.run_command('accept')
            print "UNKNOWN RESULT {}".format(result)

            result2 = yield self.run_command('ginfo')
            print("WHITE: {}".format(result2.white_name))
            print("BLACK: {}".format(result2.black_name))
            print("ME: {}".format(self.fics_user_name))
            self.me_white = result2.white_name == self.fics_user_name
            print("ME == WHITE {}".format(self.me_white))

            if self.me_white:
                self.opponent_name = result2.black_name
            else:
                self.opponent_name = result2.white_name

            time.sleep(3)
            self.tell_to(self.opponent_name, "Hello! This is ChessNet bot")
            self.tell_to(self.opponent_name, "Model info: {}".format(self.model.name))

            if self.me_white:
                yield self.move(chess.Board())

        yield self.console.show_unknown(what)

    # TODO: handle disconnect (and test on quit)

###########################################################################
# Console protocol
###########################################################################

#noinspection PyClassicStyleClass
class MyConsoleProtocol(basic.LineOnlyReceiver):
    # Console newline delimiter (LineReceiver convention)
    delimiter = '\n'
    # Actual FICS client object
    fics_client = None
    # Prompt we use
    prompt = 'fics> '

    #################################################################
    # LineReceiver virtual functions
    #################################################################

    def connectionMade(self):
        self.sendLine("============== mekk.fics console ====================================")
        self.not_parsed_notifications = open(
            NOT_PARSED_NOTIFICATIONS_FILE, mode='a', buffering=1)
        self.not_parsed_replies = open(
            NOT_PARSED_REPLIES_FILE, mode='a', buffering=1)
    def lineReceived(self, line):
        # Ignore blank lines
        if not line: return
        if not self.fics_client:
            self.sendLine("Can't execute command, not connected to FICS")
        self.execute_command(line.strip("\r\n "))

    def connectionLost(self, reason=None):
        #noinspection PyUnresolvedReferences
        if reactor.running:
            reactor.stop()

    #################################################################
    # APIs used from our client and from functions above
    #################################################################

    def register_fics_client(self, fics_client, fics_username):
        self.fics_client = fics_client
        self.sendLine(">>> Connected to fics as %s. Type commands to execute them." % fics_username)
        self.transport.write(self.prompt)

    def show_information(self, what, args):
        self.sendLine("") # close prompt
        self.sendLine(">>>[%s]>>> %s " % (what, str(args)))
        self.transport.write(self.prompt)
        return defer.succeed(None)

    def show_unknown(self, what):
        self.not_parsed_notifications.write("""
'''%s''',
""" % what)
        self.sendLine("") # close prompt
        self.sendLine(">>>[UNKNOWN]>>> %s " % what)
        self.transport.write(self.prompt)
        return defer.succeed(None)

    @defer.inlineCallbacks
    def execute_command(self, line):
        try:
            command_name, result = yield self.fics_client.run_command_ext(line)
            if command_name == "unknown" or (type(result) is UnknownReply):
                self.not_parsed_replies.write("""
{
    'input': '%s',
    'command_code': %d,
    'reply_text': '''%s'''
},
""" % (line, result.command_code, result.reply_text))
            self.sendLine("###[%s/%s]>>> Got reply:\n%s" % (line, command_name, pprint.pformat(result)))
        except Exception as e:
            self.sendLine("###[%s]>>> FAILED %s(%s)" % (line, e.__class__.__name__, str(e)))
        self.transport.write(self.prompt)


#################################################################################
# Startup glue code
#################################################################################

if __name__ == "__main__":

    if "debug" in sys.argv:
        log_level=logging.DEBUG
    else:
        log_level=logging.WARN
    logging.basicConfig(level=log_level)

    cn = chessnet.ChessNet(load_model_filename=sys.argv[1], move_temp=0.01)
    my_console = MyConsoleProtocol()
    my_client = MyFicsClient(my_console, cn)
    reactor.connectTCP(
        FICS_HOST, FICS_PORT,
        fics_connector.FicsFactory(client=my_client,
                                   auth_username=FICS_USER, auth_password=FICS_PASSWORD)
        )
    stdio.StandardIO(my_console)
    reactor.run()
