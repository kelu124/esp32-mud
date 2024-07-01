#!/usr/bin/env python

"""A simple Multi-User Dungeon (MUD) game. Players can talk to each
other, examine their surroundings and move between rooms.

Some ideas for things to try adding:
    * More rooms to explore
    * An 'emote' command e.g. 'emote laughs out loud' -> 'Mark laughs
        out loud'
    * A 'whisper' command for talking to individual players
    * A 'shout' command for yelling to players in all rooms
    * Items to look at in rooms e.g. 'look fireplace' -> 'You see a
        roaring, glowing fire'
    * Items to pick up e.g. 'take rock' -> 'You pick up the rock'
    * Monsters to fight
    * Loot to collect
    * Saving players accounts between sessions
    * A password login
    * A shop from which to buy items

author: Mark Frimston - mfrimston@gmail.com
"""

import time
import socket
import sys
import json

if sys.platform in ["esp", "WiPy"]:
    import gc
    import micropython
# import the MUD server class
from mudserver import MudServer


# structure defining the rooms in the game. Try adding more rooms to the game!
from rms import rooms

# stores the players in the game
players = {}

# start the server
mud = MudServer()
print("== MUD Starting ==")


def look(id):
    # store the player's current room
    rm = rooms[players[id]["room"]]

    # send the player back the description of their current room
    mud.send_message(id, "\n==== "+players[id]["room"]+" ====\n")
    mud.send_message(id, rm["description"]+"\n")

    playershere = []
    # go through every player in the game
    for pid, pl in players.items():
        # if they're in the same room as the player
        if players[pid]["room"] == players[id]["room"]:
            # ... and they have a name to be shown
            if players[pid]["name"] is not None:
                # add their name to the list
                playershere.append(players[pid]["name"])

    # send player a message containing the list of players in the room
    mud.send_message(id, "> Players here: {}".format(", ".join(playershere)))

    # send player a message containing the list of exits from this room
    mud.send_message(id, "> Exits are: {}\n".format(", ".join(rm["exits"])))
    return 1

def save():
    players_json = json.dumps(players, indent=3)
    with open("players_backup.json","w") as f:
        f.write(players_json)
    rooms_json = json.dumps(rooms, indent=3)
    with open("rooms_backup.json","w") as f:
        f.write(rooms_json)
    return 1

# main game loop. We loop forever (i.e. until the program is terminated)
countTicks = 0

while True:

    # pause for 1/5 of a second on each loop, so that we don't constantly
    # use 100% CPU time
    time.sleep(0.2)
    countTicks =+1
    countTicks = countTicks % 1500  # 1500*0.2 = 300s = 5 mins
    if not countTicks:
        save()
    # 'update' must be called in the loop to keep the game running and give
    # us up-to-date information
    mud.update()

    # go through any newly connected players
    for id in mud.get_new_players():

        # add the new player to the dictionary, noting that they've not been
        # named yet.
        # The dictionary key is the player's id number. We set their room to
        # None initially until they have entered a name
        # Try adding more player stats - level, gold, inventory, etc
        players[id] = {
            "name": None,
            "room": None,
        }

        # send the new player a prompt for their name
        mud.send_message(id, "What is your name?")

    # go through any recently disconnected players
    for id in mud.get_disconnected_players():

        # if for any reason the player isn't in the player map, skip them and
        # move on to the next one
        if id not in players:
            continue

        # go through all the players in the game
        for pid, pl in players.items():
            # send each player a message to tell them about the diconnected
            # player
            mud.send_message(pid, "{} quit the game".format(players[id]["name"]))

        # remove the player's entry in the player dictionary
        del players[id]

    # go through any new commands sent from players
    for id, command, params in mud.get_commands():
        print("id, command, params", id, command, params)
        # if for any reason the player isn't in the player map, skip them and
        # move on to the next one
        if id not in players:
            continue

        # if the player hasn't given their name yet, use this first command as
        # their name and move them to the starting room.
        if players[id]["name"] is None:

            players[id]["name"] = command
            players[id]["room"] = "Tavern"
            players[id]["remember"] = ["Tavern"]
            # go through all the players in the game
            for pid, pl in players.items():
                # send each player a message to tell them about the new player
                mud.send_message(pid, "{} entered the game".format(players[id]["name"]))

            # send the new player a welcome message
            mud.send_message(
                id,
                "Welcome to the game, {}. ".format(players[id]["name"])
                + "Type 'help' for a list of commands. Have fun!",
            )
            look(id)
            # send the new player the description of their current room
            mud.send_message(id, rooms[players[id]["room"]]["description"])

        # each of the possible commands is handled below. Try adding new
        # commands to the game!

        # 'help' command
        elif command == "goto":
            name = params.strip()
            if name in rooms.keys():
                players[id]["room"] = name
                mud.send_message(id, "You arrive in the place called '"+name+"'.")
                look(id)
                if name not in players[id]["remember"]:
                    players[id]["remember"].append(players[id]["room"])
                    players[id]["remember"] = list(set(players[id]["remember"]))
            else:
                mud.send_message(id, "It seems you can't reach there.")
        elif command == "help":

            # send the player back the list of possible commands
            mud.send_message(id, "Commands - explore:")
            mud.send_message(
                id, "  say <message>  - Says something out loud, " + "e.g. 'say Hello'"
            )
            mud.send_message(
                id, "  look, l        - Examines the " + "surroundings, e.g.\n    'look'"
            )
            mud.send_message(
                id, "  : <emote>      - broadcasts an emote to the room"
            )
            mud.send_message(
                id,
                "  go <exit>      - Moves through the exit "
                + "specified, e.g.\n    'go outside'",
            )
            mud.send_message(
                id, "  goto      - you go to one of the rooms"
            )
            mud.send_message(id, "\nCommands - build:")
            mud.send_message(
                id, "  create      - creates a new room. eg:\n    'create the office'"
            )      
            mud.send_message(
                id, "  link  A - B - links current room to target room, eg:"
            )  
            mud.send_message(id, "    'link the office - office door'")
            mud.send_message(
                id, "  describe    - changes the description of the current room"
            )        
            mud.send_message(
                id, "  review      - changes the description of the current room"
            )   
        # 'say' command
        elif command == "say":

            # go through every player in the game
            for pid, pl in players.items():
                # if they're in the same room as the player
                if players[pid]["room"] == players[id]["room"]:
                    # send them a message telling them what the player said
                    mud.send_message(
                        pid, "{} says: {}".format(players[id]["name"], params)
                    )

        elif command == ":":

            # go through every player in the game
            for pid, pl in players.items():
                # if they're in the same room as the player
                if players[pid]["room"] == players[id]["room"]:
                    # send them a message telling them what the player said
                    mud.send_message(
                        pid, "{} {}".format(players[id]["name"], params)
                    )


        # 'look' command
        elif command == "create":
            name = params.strip()
            if params not in rooms.keys():
                rooms[params] = {
                    "description": "This is the empty '" + params + "' room.\nSomeone should change this name.",
                    "exits": {},
                }
                mud.send_message(id, ">> You create the room '" + params + "'.")
            else:
                mud.send_message(id, ">> The room '" + params + "' already exists.")

        elif command == "describe":
            desc = params.strip()
             # store the player's current room
            rm = rooms[players[id]["room"]]
            rm["description"] = desc
            mud.send_message(id, ">> You reshaped the current room.")

        elif command == "link":
            links = [x.strip() for x in params.strip().split(" - ")]
            if len(links) == 2:
                # store the player's current room
                if not links[0] in rooms.keys():
                    mud.send_message(id, ">> You cannot point to the '"+links[0]+"' room.")
                else:
                    rm = players[id]["room"]
                    EXITS = rooms[rm]["exits"]
                    rooms[rm]["exits"][links[1]] = links[0]
                    mud.send_message(id, ">> You connected the current room to '"+links[0]+"' through the '"+links[1]+"' exit.")
            else:
                mud.send_message(id, ">> You cannot point to the '"+links[0]+"' room.\nUse 'link Tavern - enter portal")

        elif command in ["look","l"]:

            look(id)

        elif command in ["save"]:
            save()
            mud.send_message(id, ">> You feel the world is getting more stable")

        # 'go' command
        elif command == "go":

            # store the exit name
            ex = params.lower()

            # store the player's current room
            rm = rooms[players[id]["room"]]

            # if the specified exit is found in the room's exits list
            if ex in rm["exits"]:

                # go through all the players in the game
                for pid, pl in players.items():
                    # if player is in the same room and isn't the player
                    # sending the command
                    if players[pid]["room"] == players[id]["room"] and pid != id:
                        # send them a message telling them that the player
                        # left the room
                        mud.send_message(
                            pid, "{} left via exit '{}'".format(players[id]["name"], ex)
                        )

                # update the player's current room to the one the exit leads to
                players[id]["room"] = rm["exits"][ex]
                rm = rooms[players[id]["room"]]
                if rm not in players[id]["remember"]:
                    players[id]["remember"].append(players[id]["room"])
                    players[id]["remember"] = list(set(players[id]["remember"]))

                # go through all the players in the game
                for pid, pl in players.items():
                    # if player is in the same (new) room and isn't the player
                    # sending the command
                    if players[pid]["room"] == players[id]["room"] and pid != id:
                        # send them a message telling them that the player
                        # entered the room
                        mud.send_message(
                            pid,
                            "{} arrived via exit '{}'".format(players[id]["name"], ex),
                        )

                # send the player a message telling them where they are now
                mud.send_message(id, "You arrive at '{}'".format(players[id]["room"]))
                look(id)
            # the specified exit wasn't found in the current room
            else:
                # send back an 'unknown exit' message
                mud.send_message(id, "Unknown exit '{}'".format(ex))
        elif command == "remember":

            mud.send_message(id, "\nYou remember the following places:\n* "+"\n* ".join(players[id]["remember"])+"\n")

        elif command == "review":
            rooms[players[id]["room"]]["description"] = params
            # go through all the players in the game
            mud.send_message(
                id, "You remodel the '{}' room.".format(players[id]["room"])
            )
            for pid, pl in players.items():
                # if player is in the same (new) room and isn't the player
                # sending the command
                if players[pid]["room"] == players[id]["room"] and pid != id:
                    # send them a message telling them that the player
                    # entered the room
                    mud.send_message(
                        pid, "{} remodeled the room.".format(players[id]["name"])
                    )

        # some other, unrecognised command
        else:
            # send back an 'unknown command' message
            mud.send_message(id, "Unknown command '{}'".format(command))
