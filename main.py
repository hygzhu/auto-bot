import discord
import random
import asyncio
import logging
import sys
import os
import time
import shutil
import easyocr
import requests
from rapidfuzz import process
from rapidfuzz import fuzz
from util import *
from os import listdir
from os.path import isfile, join
from ocr import *
from ocr import *
from util import *
from wishlistdb import *
import json
from datetime import datetime, time
import pytz
import argparse
import time

logging.basicConfig(
    format='%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO,
        handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"output.log.{datetime.now().timestamp()}", mode="w"),
    ])

karuta_name = "Karuta"
karuta_id = 646937666251915264

SECONDS_FOR_GRAB = 6623
SECONDS_FOR_DROP = 1816

parser = argparse.ArgumentParser("parser")
parser.add_argument("-c", required=True, help="Config location", type=str)
parser.add_argument("-drop", help="Enable drop",  action='store_true')
parser.add_argument("-ocr", help="Enable ocr on public drop",  action='store_true')
args = parser.parse_args()

logging.info(f"Parser args config:{args.c} drop:{args.drop} enableocr: {args.ocr}")

ENABLE_OCR = args.ocr
DROP_STATUS = args.drop

f = open(args.c)
data = json.load(f)
token = data["token"]
author_name = data["name"]
id = data["id"]
dm_channel = data["dm_channel"]
drop_channel = data["drop_channel"]
follow_channels = data["follow_channels"]

MAX_FRUITS = 5

reader = easyocr.Reader(['en']) # this needs to run only once to load the model into memory
match = "(is dropping [3-4] cards!)|(I'm dropping [3-4] cards since this server is currently active!)"
path_to_ocr = "temp"

def is_hour_between(start, end, now):
    is_between = False

    is_between |= start <= now <= end
    is_between |= end < start and (start <= now or now <= end)

    return is_between


class MyClient(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.timer = 0
        self.grab = False
        self.drop = False
        self.grab_cd = 0
        self.drop_cd = 0
        self.seriesDB = queryWishList("SELECT DISTINCT series FROM cardinfo ORDER BY wishlistcount desc, series asc, character asc")
        self.characterDB = queryWishList("SELECT DISTINCT character FROM cardinfo WHERE wishlistcount > 1 ORDER BY wishlistcount desc, series asc, character asc")
        self.unpopCharacterDB = queryWishList("SELECT DISTINCT character FROM cardinfo WHERE wishlistcount < 2 ORDER BY wishlistcount desc, series asc, character asc")
        self.fruits = 0
        self.sleeping = False
        self.evasion = False
        self.lock = asyncio.Lock()


    async def drop_card(self):
        channel = self.get_channel(drop_channel)
        if self.timer != 0:
            await asyncio.sleep(self.timer)
            self.timer = 0
        async with channel.typing():
            await asyncio.sleep(random.uniform(0.2, 1))
        await channel.send("kd")
        self.timer += random.uniform(0.2, 1)
        self.drop = False
        self.drop_cd += SECONDS_FOR_DROP + random.uniform(4, 243)
        self.grab_cd = 0
        logging.info(f"Auto Dropped Cards")
        
        
    async def afterclick(self):
        logging.info(f"Clicked on Button")
        self.timer += 60

    async def on_ready(self):
        logging.info('Logged on as %s', self.user)

        # Dm setup
        dm = await self.get_user(karuta_id).create_dm()

        # Auto drop
        while True:

            logging.info(f"Polling  grab:{self.grab} grabcd:{self.grab_cd} drop:{self.drop} dropcd:{self.drop_cd}")
            await asyncio.sleep(random.uniform(5, 10))
            

            if self.timer != 0:
                await asyncio.sleep(self.timer)
                self.timer = 0

            utc = pytz.utc
            now = datetime.now(tz=utc)
            eastern = pytz.timezone('US/Eastern')
            loc_dt = now.astimezone(eastern)
            hour = loc_dt.hour

            while is_hour_between(hour, 1, 6):
                sleep_time = random.uniform(100, 600)
                logging.info(f"Hour is {hour} Sleeping for  {sleep_time}")
                self.sleeping = True
                await asyncio.sleep()
            self.sleeping = False

            try: 
                async with dm.typing():
                    await asyncio.sleep(random.uniform(0.2, 1))

                    if not self.grab and self.grab_cd == 0:
                        await dm.send("kcd")
                        logging.info("Checking cooldowns")
                        await asyncio.sleep(random.uniform(2, 5))

                    if DROP_STATUS:
                        if self.grab and self.drop:
                            await self.drop_card()
                
                
                if self.grab_cd != 0:
                    logging.info(f"Grab on cd {self.grab_cd}, waiting")
                    await asyncio.sleep(self.grab_cd)
                    self.grab_cd = 0
                    self.grab = True

            except Exception as e:
                logging.error(e)


    
    async def on_message(self, message: discord.Message):
        
        # Early return
        cid = message.channel.id
        if (cid not in follow_channels or cid != dm_channel) and message.author.id != karuta_id:
            return
        if self.sleeping:
            return

        async with self.lock:
            logging.debug("Processing new message!")
            # process each message atomically -> no race conditions
            await self.on_message_helper(message)
        logging.debug("Done new message!")
            

    async def on_message_helper(self, message: discord.Message):

        if self.sleeping:
            return
        
        # Early return
        cid = message.channel.id
        if (cid not in follow_channels or cid != dm_channel) and message.author.id != karuta_id:
            return

        # Edit check helper
        def mcheck(before, after):
            if len(after.components) == 0:
                return False

            if before.id == message.id and not after.components[0].children[0].disabled:
                logging.debug("Message edit found")
                try:
                    self.buttons = after.components[0].children
                    return True
                except IndexError:
                    logging.error(f"Index error")
            else:
                return False
        
        # Dm messages
        if not message.guild and message.author.id == karuta_id:
            logging.info("Got dm")
            if len(message.embeds) == 0:
                if "Your grab is now off cooldown" in  message.content:
                    self.grab = True
                    self.grab_cd = 0
                    logging.info("Grab off cd!")
                
                if "Your drop is now off cooldown" in  message.content:
                    self.drop = True
                    self.drop_cd = 0
                    logging.info("drop off cd!")
                return
            
            #Run kevent reply - rtefresh fruit count
            if message.embeds and "Gather fruit pieces to place on the board below." in message.embeds[0].description:
                logging.info("Refreshing fruit")
                self.fruits = 0
                return

            if message.embeds and "Showing cooldowns" in message.embeds[0].description:
                logging.info("Getting cooldowns")
                message_tokens = message.embeds[0].description.split("\n")
                grab_status = message_tokens[-2]
                drop_status = message_tokens[-1]
                self.grab =  "currently available" in grab_status
                self.drop = "currently available" in drop_status
            
                if not self.grab:
                    grab_time = grab_status.split("`")[1]
                    val = grab_time.split(" ")[0]
                    unit = grab_time.split(" ")[1]
                    seconds_for_grab = SECONDS_FOR_GRAB
                    if unit == "minutes":
                        seconds_for_grab = int(val)*60
                    else:
                        seconds_for_grab = int(val)
                    self.grab_cd = seconds_for_grab + random.uniform(5, 30)
                else:
                    self.grab_cd = random.uniform(5, 25)
                if not self.drop:
                    drop_time = drop_status.split("`")[1]
                    val = drop_time.split(" ")[0]
                    unit = drop_time.split(" ")[1]
                    seconds_for_drop = SECONDS_FOR_DROP
                    if unit == "minutes":
                        seconds_for_drop = int(val)*60
                    else:
                        seconds_for_drop = int(val)
                    drop_time = drop_status.split("`")[1]
                    self.drop_cd = seconds_for_drop + random.uniform(5, 30)

                logging.info(f"Grab: {self.grab}, Drop: {self.drop}")
                logging.info(f"Grab cd : {self.grab_cd}, Drop cd: {self.drop_cd}")
                

        # Message in channel
        if cid in follow_channels:

            message_content = message.content
            message_uuid = message.author.id

            if str(id) in message_content:
                logging.debug(f"Message with id - content: {message_content}")

            # karuta message for fruit
            if message_uuid == karuta_id and f"<@{str(id)}>, you gathered a fruit piece" in message_content:
                self.fruits += 1
                logging.info(f"got a fruit {self.fruits}")
    
            #took a card- grab goes on cd
            if message_uuid == karuta_id and (f"<@{str(id)}> took the" in message_content or f"<@{str(id)}> fought off" in message_content):
                logging.info(f"Took a card: message {message_content}")

                if self.evasion:
                    logging.info("No cd, evasion used")
                    self.evasion = False
                else:
                    self.grab = False
                    self.grab_cd = SECONDS_FOR_GRAB + random.uniform(0.55, 60)

            # Evasion
            if message_uuid == karuta_id and f"<@{str(id)}>, your **Evasion** blessing has activated" in message_content:
                logging.info("Evasion activated")
                self.grab = True
                self.grab_cd = 0
                self.evasion = True
            

            if message_uuid == karuta_id and f"<@{str(id)}>, you must wait" in message_content:
                if "before grabbing" in message_content:
                    grab_time = message_content.split("`")[1]
                    val = grab_time.split(" ")[0]
                    unit = grab_time.split(" ")[1]
                    seconds_for_grab = 660
                    if unit == "minutes":
                        seconds_for_grab = int(val)*60
                    else:
                        seconds_for_grab = int(val)
                    grab_delay= seconds_for_grab + random.uniform(30, 100)
                    logging.info(f"Got grab warning - updating grab cd to {grab_delay}")
                    self.grab_cd = grab_delay
                    self.grab = False

                if "before dropping" in message_content:
                    drop_time = message_content.split("`")[1]
                    val = drop_time.split(" ")[0]
                    unit = drop_time.split(" ")[1]
                    seconds_for_drop = 60*30
                    if unit == "minutes":
                        seconds_for_drop = int(val)*60
                    else:
                        seconds_for_drop = int(val)
                    drop_delay = seconds_for_drop + random.uniform(30, 100)
                    logging.info(f"Got drop warning - updating drop cd to {drop_delay}")
                    self.drop_cd = drop_delay
                    self.drop = False


            # Karuta message for personal drop
            if message_uuid == karuta_id and str(id) in message_content:
                components = message.components
                if len(components) > 0:
                    logging.info("Personal drop")
                    first_row = components[0]
                    buttons : list[discord.Button] = first_row.children
                    best_index, rating = await self.get_best_card_index(message)
                    try:
                        await self.wait_for("message_edit", check=mcheck, timeout=3)
                    except TimeoutError as e:
                        logging.error(f"Wait for timed out {e}")
                    click_delay = random.uniform(0.2, 0.8)
                    if rating == 4:
                        click_delay = random.uniform(0.01, 0.1)
                    new_button = message.components[0].children[best_index]
                    await asyncio.sleep(click_delay)
                    logging.info(f"Clicking button {best_index+1} after delay of {click_delay}")
                    await new_button.click()
                    self.grab = False
                    self.grab_cd = SECONDS_FOR_GRAB + random.uniform(0.55, 60)

                    # Get fruits
                    if message.components[0].children[-1].emoji.name == "🍉":
                        logging.info("fruit detected")
                        if self.fruits < MAX_FRUITS:
                            logging.info("grabbing fruit")
                            click_delay = random.uniform(0.55, 1)
                            await asyncio.sleep(click_delay)
                            fruit_button = message.components[0].children[-1]
                            await fruit_button.click()
                        else:
                            logging.info("skipping fruit")


                    await self.afterclick()

            if message_uuid == karuta_id and f"<@{str(id)}>, your **Generosity** blessing has activated" in message_content:
                logging.info("Generosity activated")
                self.drop = True
                self.drop_cd = 0
                
            # Free drop
            if message_uuid == karuta_id and "since this server is currently active" in message.content:
                logging.info("Got message from public drop")
                if len(message.attachments) <= 0:
                    return
                components = message.components

                waited_for_edit = False

                if self.grab and not self.drop:
                    if len(components) > 0:
                        click_delay = random.uniform(0.55, 1.2)
                        rating = 10
                        best_index = random.randint(0, len(components)-1)
                        if ENABLE_OCR:
                            best_index, rating = await self.get_best_card_index(message)
                            click_delay = random.uniform(0.2, 0.5)
                            if rating == 4:
                                click_delay = random.uniform(0.1, 0.2)
                                logging.info(f"Clicking fast {click_delay}")
                        try:
                            await self.wait_for("message_edit", check=mcheck, timeout=3)
                        except TimeoutError as e:
                            logging.error(f"Wait for timed out {e}")

                        waited_for_edit = True
                        logging.info("Lets try to grab - drop is on cd")
                        first_row = components[0]
                        if rating < 2:
                            logging.info("Rating too low, skipping")
                        else:
                            logging.info("Rating good, lets grab")
                            new_button = message.components[0].children[best_index]
                            await asyncio.sleep(click_delay)
                            logging.info(f"Clicking button {best_index+1} after delay of {click_delay}")
                            await new_button.click()
                            self.grab = False
                            self.grab_cd = 65 + random.uniform(0.55, 10)
                            await self.afterclick()
                    else:
                        logging.error("No components in drop message")
                else:
                    logging.info(f"Cannot grab, on cd {self.grab_cd}")

                if len(components) > 0:
                    # Get fruits
                    if message.components[0].children[-1].emoji.name == "🍉":
                        logging.info("fruit detected - public drop")

                        if not waited_for_edit:
                            try:
                                await self.wait_for("message_edit", check=mcheck, timeout=3)
                            except TimeoutError as e:
                                logging.error(f"Wait for timed out {e}")
                            waited_for_edit = True

                        if self.fruits < MAX_FRUITS:
                            click_delay = random.uniform(0.55, 1)
                            await asyncio.sleep(click_delay)
                            fruit_button = message.components[0].children[-1]
                            await fruit_button.click()
                            await asyncio.sleep(click_delay)
                            logging.info("Tried to grab fruit")
                        else:
                            logging.info("skipping fruit")


    async def get_best_card_index(self, message):
        start = time.time()

        rating = 0

        cardnum = extractNumCardsFromMessage(message.content)
        tempPath = f"temp/{message.id}"
        os.makedirs(tempPath, exist_ok = True)
        dropsPath = os.path.join(tempPath, "drops.webp")
        with open(dropsPath, "wb") as file:
            file.write(requests.get(message.attachments[0].url).content)
        ocrPath = os.path.join(tempPath, "ocr")
        processedImgResultList = await preProcessImg(tempPath, dropsPath, ocrPath, cardnum)
        cardList = []
        for cardImageResult in processedImgResultList:
            charNameFromOcr = ' '.join(reader.readtext(cardImageResult[0], detail=0))
            seriesOriginal = ' '.join(reader.readtext(cardImageResult[1], detail=0))
            seriesNameFromOcr = f"{seriesOriginal[:46]}..."
            ogReadPrint = reader.readtext(cardImageResult[2], detail=0, allowlist ='0123456789.')[0]
            printNumFromOcr = int(str.split(ogReadPrint,".")[0])

            print_val = -1
            if printNumFromOcr < 100:
                print_val = 4
                rating = max(rating, 3)
                logging.info(f"Wow low print name: {charNameFromOcr} series: {seriesNameFromOcr} print: {printNumFromOcr}")
            elif printNumFromOcr < 1000:
                print_val = 3
                rating = max(rating, 2)
            elif printNumFromOcr < 10000:
                print_val = 2
            elif printNumFromOcr < 10000:
                print_val = 1
            elif printNumFromOcr < 50000:
                print_val = 0

            cardList.append((charNameFromOcr, seriesNameFromOcr, printNumFromOcr, print_val))
        logging.debug(f"Cardlist: {cardList}")

        # Query for the series/char.
        results = []
        
        for cardPos, (cardChar, cardSeries, cardPrint, print_val) in enumerate(cardList):
            found, matchedSeries, matchedChar, wishlistCount = self.findBestMatch(cardSeries, cardChar)
            
            wishlist_val = 0
            if wishlistCount > 1000:
                wishlist_val = 4
                rating = max(rating, 4)
                logging.info(f"Wow high WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 500:
                wishlist_val = 3
                rating = max(rating, 3)
                logging.info(f"medium WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 100:
                wishlist_val = 2
                rating = max(rating, 2)
                logging.info(f"ok WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 10:
                wishlist_val = 1
            
            results.append((wishlist_val, wishlistCount))
        logging.debug(f"Results: {results}")

        decision = []

        for card, wishlist in zip(cardList, results):
            decision.append({
                "name": card[0],
                "series": card[1],
                "printcount": card[2],
                "print": card[3],
                "wl": wishlist[0],
                "wlcount": wishlist[1]
            })

        logging.info(f"Cards analyzed:\n{"\n".join([str(dec) for dec in decision])}")
        best_card = decision[0]
        best_idx = 0
        for idx, card in enumerate(decision):
            if card["wl"] > best_card["wl"]:
                best_card = card
                best_idx = idx
            if card["wl"] == best_card["wl"]:
                if card["print"] > best_card["print"]:
                    best_card = card
                    best_idx = idx

            if card["wl"] == best_card["wl"] and card["print"] == best_card["print"]:
                if card["wlcount"] > best_card["wlcount"]:
                    best_card = card
                    best_idx = idx
                if card["wlcount"] == best_card["wlcount"]:
                    if card["printcount"] < best_card["printcount"]:
                        best_card = card
                        best_idx = idx

        
        logging.info(f"Best card is idx {best_idx}")

        end = time.time()
        logging.info(f"Took {end-start} time to get best index")

        return best_idx, rating


    # Finds the best match by series first, then character with >1 wishlists
    # Returns found, matchedseries, matchedcharacter, wishlistcount
    def findBestMatch(self, seriesToLookFor, charToLookFor) -> tuple[bool, str, str, int]:
        seriesBestMatch = process.extractOne(seriesToLookFor, self.seriesDB)
        logging.debug("Best series match: " + str(seriesBestMatch))

        # check series name first and see if we can find a matching series
        if seriesBestMatch[1] >= 70:
            matchedSeries = seriesBestMatch[0]
            characterDB = queryWishList("SELECT DISTINCT character FROM cardinfo WHERE series LIKE ? ORDER BY wishlistcount desc, series asc, character asc", (f"%{matchedSeries}%",))

            # then see if we can find a matching character from that series
            charBestMatch = process.extractOne(charToLookFor, characterDB)
            logging.debug("Best Series Match >= 70, Best char match: " + str(charBestMatch))
            
            # if the character is also close enough, that works
            if charBestMatch[1] >= 70 or (seriesBestMatch[1] >= 90 and charBestMatch[1] >= 65):
                matchedChar = charBestMatch[0]
                queryResult = queryWishList("SELECT DISTINCT wishlistcount FROM cardinfo WHERE series = ? and character = ? ORDER BY wishlistcount desc, series asc, character asc", (matchedSeries, matchedChar,))
                if len(queryResult) > 0:
                    wishlistcount = queryResult[0]
                    logging.debug("Best match: " + matchedChar + " from " + matchedSeries)
                    return (True, matchedSeries, matchedChar, wishlistcount)
                # if we matched the series but can't find a character, they're probably not important
                # elif seriesBestMatch[1] >= 90:
                #     foundAny = True
                #     resultMsg += wishlistMessage(cardpos, matchedSeries, "N/A", "???")
            # if we matched the series but can't find a character, they're probably not important
            # elif seriesBestMatch[1] >= 90:
            #     foundAny = True
            #     resultMsg += wishlistMessage(cardpos, matchedSeries, "N/A", "???")
        # Didn't match a series, must rely only on character name and find the closest series
        charBestMatch = process.extractOne(charToLookFor, self.characterDB)
        logging.debug("Best char match: " + str(charBestMatch))

        if charBestMatch[1] >= 90:
            matchedChar = charBestMatch[0]
            seriesDB = queryWishList("SELECT DISTINCT series FROM cardinfo WHERE character = ? ORDER BY wishlistcount desc, series asc, character asc", (matchedChar,))
            seriesBestMatchNarrowed = process.extractOne(seriesToLookFor, seriesDB)
            logging.debug("Best Char Match >= 90, Best series match: " + str(seriesBestMatchNarrowed))

            if seriesBestMatchNarrowed[1] >= 65:
                matchedSeries = seriesBestMatchNarrowed[0]
                queryResult = queryWishList("SELECT DISTINCT wishlistcount FROM cardinfo WHERE series = ? and character = ? ORDER BY wishlistcount desc, series asc, character asc", (matchedSeries, matchedChar,))
                if len(queryResult) > 0:
                    wishlistcount = queryResult[0]
                    logging.debug("Best match: " + matchedChar + " from " + matchedSeries)
                    return (True, matchedSeries, matchedChar, wishlistcount)
        return (False, "", "", -1)


def run():
    client = MyClient()
    client.run(token)

if __name__ == "__main__":
    run()
