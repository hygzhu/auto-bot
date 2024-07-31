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

def timetz(*args):
    return datetime.now(tz).timetuple()

tz = pytz.timezone('US/Eastern') # UTC, Asia/Shanghai, Europe/Berlin

logging.basicConfig(
    format='%(asctime)s,%(msecs)03d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.INFO,
        handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(f"output.log.{datetime.now().timestamp()}", mode="w"),
    ])

logging.Formatter.converter = lambda *args: datetime.now(tz).timetuple()

karuta_name = "Karuta"
KARUTA_ID = 646937666251915264

SECONDS_FOR_GRAB = 312
SECONDS_FOR_DROP = 1816/2

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
logging.info(f"Loaded config {data}")

TOKEN = data["token"]
AUTHOR_NAME = data["name"]
USERID = data["id"]
DM_CHANNEL = data["dm_channel"]
DROP_CHANNELS = data["drop_channels"]
FOLLOW_CHANNELS = data["follow_channels"]

MAX_FRUITS = 3

reader = easyocr.Reader(['en']) # this needs to run only once to load the model into memory
match = "(is dropping [3-4] cards!)|(I'm dropping [3-4] cards since this server is currently active!)"
path_to_ocr = "temp"

def add_grab_cd():
    return SECONDS_FOR_GRAB + random.uniform(0.55, 60)

class MyClient(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.grab = False
        self.drop = False
        self.grab_cd = 0
        self.seriesDB = queryWishList("SELECT DISTINCT series FROM cardinfo ORDER BY wishlistcount desc, series asc, character asc")
        self.characterDB = queryWishList("SELECT DISTINCT character FROM cardinfo WHERE wishlistcount > 1 ORDER BY wishlistcount desc, series asc, character asc")
        self.unpopCharacterDB = queryWishList("SELECT DISTINCT character FROM cardinfo WHERE wishlistcount < 2 ORDER BY wishlistcount desc, series asc, character asc")
        self.fruits = 0
        self.sleeping = False
        self.evasion = False
        self.generosity = False
        self.lock = asyncio.Lock()
        self.last_dropped_channel = random.choice(DROP_CHANNELS)
        self.last_hour = 0
        self.dropped_cards_awaiting_pickup = False

    async def drop_card(self):

        self.drop = False

        new_channels = list(set(DROP_CHANNELS) - set([self.last_dropped_channel]))
        selected_channel = random.choice(new_channels)

        # TODO clan override
        selected_channel = random.choice([1006000542578901052, 1006000542578901052, 1006000542578901052, selected_channel])

        self.last_dropped_channel = selected_channel
        channel = self.get_channel(selected_channel)

        await asyncio.sleep(random.uniform(2, 4))

        async with channel.typing():
            await asyncio.sleep(random.uniform(0.2, 1))
        logging.info(f"-----------------------Dropping in channel {selected_channel}-----------------------")
        await channel.send("kd")
        self.dropped_cards_awaiting_pickup = True

    async def add_short_delay(self):
        short_delay = random.uniform(3, 8)
        logging.info(f"Creating short delay of {short_delay}")
        await asyncio.sleep(short_delay)
        
    async def on_ready(self):
        logging.info('Logged on as %s', self.user)
        # Dm setup
        dm = await self.get_user(KARUTA_ID).create_dm()

        # Auto drop
        while True:

            logging.info(f"Polling  grab:{self.grab} drop:{self.drop}  grab cd:{self.grab_cd}")
            await asyncio.sleep(random.uniform(5, 10))
            
            # Sleeping time
            utc = pytz.utc
            now = datetime.now(tz=utc)
            eastern = pytz.timezone('US/Eastern')
            loc_dt = now.astimezone(eastern)
            hour = loc_dt.hour
            while is_hour_between(1, 6, hour):
                utc = pytz.utc
                now = datetime.now(tz=utc)
                eastern = pytz.timezone('US/Eastern')
                loc_dt = now.astimezone(eastern)
                hour = loc_dt.hour
                sleep_time = random.uniform(100, 600)
                logging.info(f"Hour is {hour} Sleeping for  {sleep_time}")
                self.sleeping = True
                await asyncio.sleep(sleep_time)
            self.sleeping = False

            #take a break
            # break_time = False
            # if hour != self.last_hour:
            #     break_time = random.randint(1,3) == 1
            # if break_time:
            #     logging.info("Time for a break!!")
            #     sleep_time = random.uniform(500, 900)
            #     logging.info(f"break for  {sleep_time}")          
            #     self.sleeping = True
            #     await asyncio.sleep(sleep_time)
            #     self.sleeping = False
            # else:
            #     logging.info("No breaks!!")
            # self.last_hour = hour

            # Do something
            try: 
                # Using shared vars here - need lock
                async with self.lock:

                    if not self.grab and self.grab_cd == 0:
                        
                        logging.info("Checking cooldowns")
                        async with dm.typing():
                            await asyncio.sleep(random.uniform(0.2, 1))
                        logging.info(f"-----------------------Sending in channel DM-----------------------")
                        await dm.send("kcd")
                        await asyncio.sleep(random.uniform(2, 5))

                    if DROP_STATUS:
                        if self.grab and self.drop:
                            logging.info(f"Try to drop")
                            await self.drop_card()
                        
                    
                if self.grab_cd != 0:
                    logging.info(f"Grab on cd {self.grab_cd}, waiting")
                    og_grab_cd = self.grab_cd
                    await asyncio.sleep(self.grab_cd)
                    # Using shared vars here - need lock
                    async with self.lock:
                        if self.grab_cd == og_grab_cd:
                            logging.info(f"Grab cd didnt change, setting to 0")
                            # Race condition, need to check grab cd didnt change
                            self.grab_cd = 0
                            logging.info(f"Grab cd set to {self.grab_cd}")
                            self.grab = True
                        else:
                            logging.info(f"Grab cd changed")

                else:
                    #just wait a few before looping
                    logging.info(f"Wait a few before looping")
                    await asyncio.sleep(random.uniform(2, 5))

            except Exception as e:
                logging.error(e)

    async def on_message(self, message: discord.Message):
        
        # Early return
        cid = message.channel.id
        if (cid not in FOLLOW_CHANNELS + [DM_CHANNEL]):
            return
        if message.author.id != KARUTA_ID:
            return
        if self.sleeping:
            logging.debug("I'm sleeping!")
            return

        async with self.lock:
            logging.debug("Processing new message!")
            # process each message atomically -> no race conditions
            await self.on_message_helper(message)
        logging.debug("Done new message!")

    def check_for_dm(self, message):
        # Dm messages
        if not message.guild and message.author.id == KARUTA_ID:
            logging.info("Got dm")
            if len(message.embeds) == 0:
                if "Your grab is now off cooldown" in  message.content:
                    self.grab = True
                    self.grab_cd = 0
                    logging.info("Grab off cd!")
                
                if "Your drop is now off cooldown" in  message.content:
                    self.drop = True
                    logging.info("drop off cd!")
                return
            
            #Run kevent reply - rtefresh fruit count
            if len(message.embeds) > 0 and "Gather fruit pieces to place on the board below." in message.embeds[0].description:
                logging.info("Refreshing fruit")
                self.fruits = 0
                return

            if len(message.embeds) > 0 and "Showing cooldowns" in message.embeds[0].description:
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
                    logging.info(f"Grab cd set to {self.grab_cd}")
                else:
                    self.grab_cd = random.uniform(5, 25)
                    logging.info(f"Grab cd set to {self.grab_cd}")
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

                logging.info(f"Grab: {self.grab}, Drop: {self.drop}")
                logging.info(f"Grab cd : {self.grab_cd}")
    
    def check_fruit_grab(self, message_uuid, message_content):
        # karuta message for fruit
        if message_uuid == KARUTA_ID and f"<@{str(USERID)}>, you gathered a fruit piece" in message_content:
            self.fruits += 1
            logging.info(f"got a fruit {self.fruits}")

    def check_for_card_grab(self, message_uuid, message_content):
        #took a card - grab goes on cd
        if message_uuid == KARUTA_ID and (f"<@{str(USERID)}> took the" in message_content or f"<@{str(USERID)}> fought off" in message_content):
            logging.info(f"Took a card: message {message_content}")

            if f"<@{str(USERID)}> fought off" in message_content:
                logging.info("!!!!!!!!!!!!!!!!!!!!!!!!!YOU FOUGHT AND WON!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

            if self.evasion:
                logging.info("No cd, evasion used")
                self.evasion = False
                self.grab = False
            else:
                self.grab = False
                self.grab_cd = add_grab_cd()
                logging.info(f"Grab cd set to {self.grab_cd}")
                logging.info(f"Updating grab cd to {self.grab_cd} since we grabbed card")

    def check_for_evasion(self, message_uuid, message_content ):
        # Evasion
        if message_uuid == KARUTA_ID and f"<@{str(USERID)}>, your **Evasion** blessing has activated" in message_content:
            logging.info("Evasion activated")
            self.grab = True
            self.grab_cd = 0
            self.evasion = True

    def check_for_cooldown_warning(self, message_uuid, message_content):
        if message_uuid == KARUTA_ID and f"<@{str(USERID)}>, you must wait" in message_content:
            if "before grabbing" in message_content:
                grab_time = message_content.split("`")[1]
                val = grab_time.split(" ")[0]
                unit = grab_time.split(" ")[1]
                seconds_for_grab = SECONDS_FOR_GRAB
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
                seconds_for_drop = SECONDS_FOR_DROP
                if unit == "minutes":
                    seconds_for_drop = int(val)*60
                else:
                    seconds_for_drop = int(val)
                drop_delay = seconds_for_drop + random.uniform(30, 100)
                logging.info(f"Got drop warning - updating drop cd to false")
                self.drop = False

    async def check_fruit_in_private_message(self, message):
        # Get fruits after
        if message.components[0].children[-1].emoji.name == "🍉":
            logging.info("fruit detected")
            if self.fruits < MAX_FRUITS:
                logging.info("grabbing fruit")
                click_delay = random.uniform(0.55, 1)
                await asyncio.sleep(click_delay)
                fruit_button = message.components[0].children[-1]
                await fruit_button.click()
                await asyncio.sleep(random.uniform(0.3, 0.6))
                logging.info(f"-----------------------PRIVATE FRUIT CLICK in {message.channel.id}-----------------------------------")
            else:
                logging.info("skipping fruit")

    async def check_fruit_in_public_message(self, message, waited_for_edit, check_for_message_button_edit):
        if message.components[0].children[-1].emoji.name == "🍉":
            logging.info("fruit detected - public drop")

            if not waited_for_edit:
                try:
                    await self.wait_for("message_edit", check=check_for_message_button_edit, timeout=3)
                except TimeoutError as e:
                    logging.error(f"Wait for timed out {e}")
                waited_for_edit = True

            random_get_fruit = random.choice([True,True,True,False])
            if random_get_fruit:
                if self.fruits < MAX_FRUITS:
                    click_delay = random.uniform(0.55, 1.5)
                    await asyncio.sleep(click_delay)
                    fruit_button = message.components[0].children[-1]
                    await fruit_button.click()
                    logging.info(f"-----------------------PUBLIC FRUIT CLICK in {message.channel.id}-----------------------------------")
                    await asyncio.sleep(click_delay)
                    logging.info("Tried to grab fruit")
                    await asyncio.sleep(random.uniform(0.3, 0.6))
                else:
                    logging.info("skipping fruit, we at max")
            else:
                logging.info("skipping fruit, random says no")

    async def click_card_button(self, message, best_index, click_delay):
        new_button = message.components[0].children[best_index]
        await asyncio.sleep(click_delay)
        logging.info(f"Clicking button {best_index+1} after delay of {click_delay}")
        await new_button.click()
        logging.info(f"-----------------------CLICK BUTTON in {message.channel.id}-----------------------------------")
        self.grab = False
        self.grab_cd = 64 + random.uniform(5, 20)
        logging.info(f"Grab cd set to {self.grab_cd}")
        await asyncio.sleep(random.uniform(0.3, 0.6))

    async def check_personal_drop(self, message_uuid, message_content, message, check_for_message_button_edit):
        # Karuta message for personal drop
        if message_uuid == KARUTA_ID and str(USERID) in message_content:
            components = message.components
            if len(components) > 0:
                logging.info("-----------------------Personal drop-----------------------")
                try:
                    best_index, rating = await self.get_best_card_index(message)
                except Exception as e:
                    logging.error(f"OCR machine broke personal {e}")
                try:
                    await self.wait_for("message_edit", check=check_for_message_button_edit, timeout=3)
                except TimeoutError as e:
                    logging.error(f"Wait for timed out {e}")
                click_delay = random.uniform(0.2, 1.2)

                if self.generosity:
                    logging.info(f"We have generosity")
                    self.drop = True
                    self.generosity = False
                    # skip grab if garbage
                    if rating > 1:
                        click_delay = random.uniform(0.8, 2)
                        logging.info(f"Rating decent {click_delay}")

                        if rating == 4:
                            logging.info(f"Clicking fast {click_delay}")
                            click_delay = random.uniform(0.1, 0.2)
                        await self.click_card_button(message, best_index, click_delay)
                        self.dropped_cards_awaiting_pickup = False
                        # Get fruits after
                        await self.check_fruit_in_private_message(message)
                    else:
                        logging.info("Rating garbage, skip due to generosity")
                        await self.check_fruit_in_private_message(message)
                else:
                    
                    logging.info(f"Dont have generosity")

                    if rating >= 2:
                        click_delay = random.uniform(0.3, 1)
                        if rating == 4:
                            click_delay = random.uniform(0.1, 0.2)
                            logging.info(f"Clicking fast {click_delay}")
                        else:
                            click_delay = random.uniform(0.3, 1)
                            logging.info(f"Clicking ok speed {click_delay}")
                        await self.click_card_button(message, best_index, click_delay)
                        self.dropped_cards_awaiting_pickup = False
                        await self.check_fruit_in_private_message(message)
                    else:
                        # Get fruits first
                        await self.check_fruit_in_private_message(message)
                        logging.info(f"Rating too low clicking slow {click_delay}")
                        click_delay = random.uniform(0.8, 3)
                        if rating < 1:
                            click_delay = random.uniform(4, 10)
                        await self.click_card_button(message, best_index, click_delay)
                        self.dropped_cards_awaiting_pickup = False
        
            await self.add_short_delay()


    def check_for_generosity(self, message_uuid, message_content ):
        if message_uuid == KARUTA_ID and f"<@{str(USERID)}>, your **Generosity** blessing has activated" in message_content:
            self.generosity = True
            logging.info(f"Generosity activated")

    async def check_public_drop(self, message_uuid, message_content, message: discord.Message, check_for_message_button_edit):
        
        if self.dropped_cards_awaiting_pickup:
            logging.info(f"Personal drop awaiting pickup")
            return
        
        if message_uuid == KARUTA_ID and "since this server is currently active" in message.content:
            logging.info("Got message from public drop")
            if len(message.attachments) <= 0:
                return
            components = message.components

            waited_for_edit = False

            if self.grab and not self.drop:
                if len(components) > 0:
                    click_delay = random.uniform(0.55, 1.5)
                    rating = 10
                    best_index = random.randint(0, len(components)-1)
                    if ENABLE_OCR:
                        try:
                            best_index, rating = await self.get_best_card_index(message)
                        except Exception as e:
                            logging.error(f"OCR machine broke public {e}")
                            return
                        click_delay = random.uniform(0.55, 1.5)
                        if rating == 4:
                            click_delay = random.uniform(0.1, 0.2)
                            logging.info(f"Clicking fast {click_delay}")
                    try:
                        await self.wait_for("message_edit", check=check_for_message_button_edit, timeout=3)
                    except TimeoutError as e:
                        logging.error(f"Wait for timed out {e}")
                    waited_for_edit = True
                    logging.info("Lets try to grab - drop is on cd")
                    if rating < 2:
                        logging.info("Rating too low, skipping")
                    else:
                        logging.info("Rating good, lets grab")
                        await self.click_card_button(message, best_index, click_delay)
                        await self.add_short_delay()
                else:
                    logging.error(f"No components in drop message, {message}")
            else:
                logging.info(f"Cannot grab, on cd")

            if len(components) > 0:
                # Get fruits
                await self.check_fruit_in_public_message(message, waited_for_edit, check_for_message_button_edit)


    async def on_message_helper(self, message: discord.Message):

        cid = message.channel.id

        # Edit check helper
        def check_for_message_button_edit(before, after):
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

        self.check_for_dm(message)

        # Message in channel
        message_content = message.content
        message_uuid = message.author.id
        if str(USERID) in message_content:
            logging.debug(f"Message with id - content: {message_content}")

        try: 
            self.check_fruit_grab(message_uuid, message_content)
            self.check_for_card_grab(message_uuid, message_content)
            self.check_for_evasion(message_uuid, message_content)
            self.check_for_cooldown_warning(message_uuid, message_content)
            await self.check_personal_drop(message_uuid, message_content, message, check_for_message_button_edit)
            self.check_for_generosity(message_uuid, message_content)
            await self.check_public_drop(message_uuid, message_content, message, check_for_message_button_edit)
        except Exception as e:
            logging.error(f"Something went wrong processing message {e}")

    async def get_best_card_index(self, message):
        start = time.time()

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

            print_rating = 0   
            print_val = -1
            if printNumFromOcr < 100:
                print_val = 4
                print_rating = 3
            elif printNumFromOcr < 1000:
                print_val = 3
                print_rating = 2
            elif printNumFromOcr < 10000:
                print_val = 2
                print_rating = 1
            elif printNumFromOcr < 10000:
                print_val = 1
            elif printNumFromOcr < 50000:
                print_val = 0

            cardList.append((charNameFromOcr, seriesNameFromOcr, printNumFromOcr, print_val, print_rating))
        logging.debug(f"Cardlist: {cardList}")

        # Query for the series/char.
        results = []
        
        for cardPos, (cardChar, cardSeries, cardPrint, print_val, printrating) in enumerate(cardList):
            found, matchedSeries, matchedChar, wishlistCount = findBestMatch(cardSeries, cardChar, self.seriesDB, self.characterDB)
            
            wishlist_val = 0
            wl_rating = 0
            if wishlistCount > 5000:
                wishlist_val = 10
                wl_rating = 10
                logging.info(f"Wow crazy WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 1000:
                wishlist_val = 9
                wl_rating = 7
                logging.info(f"Wow high WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 500:
                wishlist_val = 8
                wl_rating = 6
                logging.info(f"medium WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 100:
                wishlist_val = 7
                wl_rating = 5
                logging.info(f"small WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 30:
                wishlist_val = 7
                wl_rating = 4
                logging.info(f"tiny WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount >= 10:
                wishlist_val = 3
                wl_rating = 2
                logging.info(f"mini WL name: {cardChar} series: {cardSeries} print: {cardPrint} Wl: {wishlistCount}")
            elif wishlistCount > 5:
                wishlist_val = 2
                wl_rating = 1
            elif wishlistCount > 0:
                wishlist_val = 1
            
            results.append((wishlist_val, wishlistCount, wl_rating))
        logging.debug(f"Results: {results}")

        decision = []

        for card, wishlist in zip(cardList, results):
            decision.append({
                "name": card[0],
                "series": card[1],
                "printcount": card[2],
                "print": card[3],
                "printrating": card[4],
                "wl": wishlist[0],
                "wlcount": wishlist[1],
                "wlrating": wishlist[2],
            })


        logging.info(f"Cards analyzed:\n{"\n".join([
            f"{dec["name"] : <40}{dec["name"] : <40} WL: {dec["wlcount"] : <10} Print: {dec["printcount"]: <10}"
            for dec in decision])}")
        best_card = decision[0]
        best_idx = 0
        best_rating = 0
        for idx, card in enumerate(decision):
            
            rating = max(card["wlrating"],card["printrating"])

            if rating > best_rating:
                best_card = card
                best_idx = idx
                best_rating = rating
            else:

                if card["wl"] > best_card["wl"]:
                    best_card = card
                    best_idx = idx
                    best_rating = rating
                if card["wl"] == best_card["wl"]:
                    if card["print"] > best_card["print"]:
                        best_card = card
                        best_idx = idx
                        best_rating = rating

                if card["wl"] == best_card["wl"] and card["print"] == best_card["print"]:
                    if card["wlcount"] > best_card["wlcount"]:
                        best_card = card
                        best_idx = idx
                        best_rating = rating
                    if card["wlcount"] == best_card["wlcount"]:
                        if card["printcount"] < best_card["printcount"]:
                            best_card = card
                            best_idx = idx
                            best_rating = rating

        
        logging.info(f"Best card is idx {best_idx} with rating {best_rating}")

        end = time.time()
        logging.info(f"Took {end-start} time to get best index")

        return best_idx, best_rating


    
def run():
    client = MyClient()
    client.run(TOKEN)

if __name__ == "__main__":
    run()
