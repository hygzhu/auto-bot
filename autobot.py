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
import traceback
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
args = parser.parse_args()
logging.info(f"Parser args config:{args.c}")


def get_config_data():
    f = open(args.c)
    data = json.load(f)
    return data

data = get_config_data()

USERID = data["id"]
TOKEN = data["token"]
DM_CHANNEL = data["dm_channel"]
DROP_CHANNELS = data["drop_channels"]
FOLLOW_CHANNELS = data["follow_channels"]
MAX_FRUITS = 4


reader = easyocr.Reader(['en']) # this needs to run only once to load the model into memory
match = "(is dropping [3-4] cards!)|(I'm dropping [3-4] cards since this server is currently active!)"
path_to_ocr = "temp"

class MyClient(discord.Client):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.grab = False
        self.drop = False
        self.seriesDB = queryWishList("SELECT DISTINCT series FROM cardinfo ORDER BY wishlistcount desc, series asc, character asc")
        self.characterDB = queryWishList("SELECT DISTINCT character FROM cardinfo WHERE wishlistcount > 1 ORDER BY wishlistcount desc, series asc, character asc")
        self.unpopCharacterDB = queryWishList("SELECT DISTINCT character FROM cardinfo WHERE wishlistcount < 2 ORDER BY wishlistcount desc, series asc, character asc")
        self.fruits = 0
        self.sleeping = False
        self.evasion = 0
        self.generosity = False
        self.lock = asyncio.Lock()
        self.last_dropped_channel = random.choice(DROP_CHANNELS)
        self.last_hour = 0
        self.dropped_cards_awaiting_pickup = False
        self.timestamp_for_grab_available = datetime.now().timestamp() + 500000000000

    async def drop_card(self):

        self.drop = False

        new_channels = list(set(DROP_CHANNELS) - set([self.last_dropped_channel]))
        selected_channel = random.choice(new_channels)

        # TODO clan + public override
        selected_channel = random.choice([1006000542578901052, selected_channel] + ([1006000542578901052]*4))

        self.last_dropped_channel = selected_channel
        channel = self.get_channel(selected_channel)

        async with channel.typing():
            await asyncio.sleep(random.uniform(0.2, 1))
        logging.info(f"-----------------------Dropping in channel {selected_channel}-----------------------")
        await channel.send("kd")
        self.dropped_cards_awaiting_pickup = True

    async def add_short_delay(self):
        short_delay = random.uniform(3, 8)
        logging.debug(f"Creating short delay of {short_delay}")
        await asyncio.sleep(short_delay)

    async def check_cooldowns(self, dm):
        logging.info("Checking cooldowns")
        async with dm.typing():
            await asyncio.sleep(random.uniform(0.2, 1))
        logging.info(f"-----------------------Sending in channel DM-----------------------")
        await dm.send("kcd")
        await asyncio.sleep(random.uniform(2, 5))
    
    async def on_ready(self):
        logging.info('Logged on as %s', self.user)
        # Dm setup
        dm = await self.get_user(KARUTA_ID).create_dm()

        await self.check_cooldowns(dm)

        # Auto drop
        while True:
            
            diff= datetime.now().timestamp() - self.timestamp_for_grab_available
            logging.info(f"g:{self.grab} d:{self.drop} f: {self.fruits} grab_cd: {diff}")
            await asyncio.sleep(random.uniform(5, 10))
            
            # Sleeping time
            utc = pytz.utc
            now = datetime.now(tz=utc)
            eastern = pytz.timezone('US/Eastern')
            loc_dt = now.astimezone(eastern)
            hour = loc_dt.hour

            start_hour = random.choice([1,2])
            end_hour = random.choice([5,6])
            while is_hour_between(start_hour, end_hour, hour):
                logging.info(f" sleeping from {start_hour}, {end_hour}, {hour}")
                utc = pytz.utc
                now = datetime.now(tz=utc)
                eastern = pytz.timezone('US/Eastern')
                loc_dt = now.astimezone(eastern)
                
                utc = pytz.utc
                now = datetime.now(tz=utc)
                eastern = pytz.timezone('US/Eastern')
                loc_dt = now.astimezone(eastern)
                hour = loc_dt.hour
                sleep_time = random.uniform(600, 1200)
                logging.info(f"Hour is {hour} Sleeping for {sleep_time}")
                self.sleeping = True
                await asyncio.sleep(sleep_time)
            if self.sleeping:
                self.sleeping = False
                self.drop = True
                self.grab = True
            self.sleeping = False

            # Do something
            try: 
                # Using shared vars here - need lock
                async with self.lock:
                    
                    diff= datetime.now().timestamp() - self.timestamp_for_grab_available
                    if diff > 0:
                        logging.info(f"Grab is available now, diff={diff}")
                        self.grab = True
                        self.timestamp_for_grab_available = datetime.now().timestamp() + 500000000000


                    if self.grab and self.drop:
                        
                        logging.info(f"-----------------------Adding delay before drop-----------------------")
                        await asyncio.sleep(random.uniform(2, 10))
                        logging.info(f"Try to drop")
                        await self.drop_card()
                        

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
            logging.info("I'm sleeping!")
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
    
    def check_fruit_grab(self, message_uuid, message_content):
        # karuta message for fruit
        if message_uuid == KARUTA_ID and f"<@{str(USERID)}>, you gathered a fruit piece" in message_content:
            self.fruits += 1
            logging.info(f"got a fruit {self.fruits}")
        
        if message_uuid == KARUTA_ID and f"<@{str(USERID)}>, you have too many unused" in message_content:
            self.fruits = 10000000
            logging.info(f"FRUIT WARNING DO NOT GET MORE FRUITS")
        
    def check_for_card_grab(self, message_uuid, message_content):
        #took a card - grab goes on cd
        if message_uuid == KARUTA_ID and (f"<@{str(USERID)}> took the" in message_content or f"<@{str(USERID)}> fought off" in message_content):
            logging.info(f"Took a card: message {message_content}")

            if f"<@{str(USERID)}> fought off" in message_content:
                logging.info("!!!!!!!!!!!!!!!!!!!!!!!!!YOU FOUGHT AND WON!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

            if self.evasion:
                logging.info("evasion used")
                self.evasion -= 1
            else:
                self.grab = False
                self.timestamp_for_grab_available = datetime.now().timestamp() + SECONDS_FOR_GRAB + random.randint(2,10)
                logging.info(f"Grab  set to false")
            self.dropped_cards_awaiting_pickup = False

    def check_for_evasion(self, message_uuid, message_content ):
        # Evasion
        if message_uuid == KARUTA_ID and f"<@{str(USERID)}>, your **Evasion** blessing has activated" in message_content:
            logging.info("Evasion activated")
            self.grab = True
            self.evasion += 1

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
                logging.info(f"Got grab warning")
                self.grab = False
                self.timestamp_for_grab_available = datetime.now().timestamp() + grab_delay

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

    async def check_fruit_in_public_message(self, message: discord.Message, waited_for_edit, check_for_message_button_edit):
        if message.components[0].children[-1].emoji.name == "🍉":
            logging.info("fruit detected - public drop")

            if not waited_for_edit:
                try:
                    await self.wait_for("message_edit", check=check_for_message_button_edit, timeout=3)
                except TimeoutError as e:
                    logging.error(f"Wait for timed out {e}")
                waited_for_edit = True

            random_get_fruit = random.choice([True,True,True,True,True,False,True,True,True,True,True])
            if message.channel.id in [1251358963581063208, 1249793110012067880]:
                random_get_fruit = True

            if random_get_fruit:
                if self.fruits < MAX_FRUITS:
                    click_delay = random.uniform(0.55, 1.5)
                    await asyncio.sleep(click_delay)
                    fruit_button = message.components[0].children[-1]
                    await fruit_button.click()
                    logging.info(f"-----------------------PUBLIC FRUIT CLICK in {message.channel.id}-----------------------------------")
                    await asyncio.sleep(click_delay)
                    logging.debug("Tried to grab fruit")
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
        self.timestamp_for_grab_available = datetime.now().timestamp() + 60 +  random.randint(2,10)
        await asyncio.sleep(random.uniform(0.3, 0.6))

    async def check_personal_drop(self, message_uuid, message_content, message, check_for_message_button_edit):
        # Karuta message for personal drop
        if message_uuid == KARUTA_ID and str(USERID) in message_content and f"<@{str(USERID)}> is dropping" in message_content:
            components = message.components
            rating = 0
            if len(components) > 0:
                logging.info("-----------------------Personal drop-----------------------")
                best_index = random.randint(0,2)
                try:
                    best_index, rating = await self.get_best_card_index(message)
                except Exception as e:
                    logging.error(f"OCR machine broke personal!!!!! {e}")
                    logging.error(traceback.format_exc())

                if best_index == -1:
                    logging.error(f"Could not process image for message: {message_content}, selecting random index")
                    best_index = random.randint(0,2)

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
                    if rating >= 1:
                        click_delay = random.uniform(0.8, 2)
                        logging.info(f"Rating decent {click_delay}")
                        if rating >= 2:
                            logging.info(f"fast {click_delay}")
                            click_delay = random.uniform(0.4, 0.8)
                        if rating >= 3:
                            logging.info(f"fastest {click_delay}")
                            click_delay = random.uniform(0.2, 0.3)
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
                        if rating >= 4:
                            click_delay = random.uniform(0.2, 0.3)
                            logging.info(f" fast {click_delay}")
                        else:
                            click_delay = random.uniform(0.3, 1)
                            logging.info(f"ok speed {click_delay}")
                        await self.click_card_button(message, best_index, click_delay)
                        self.dropped_cards_awaiting_pickup = False
                        await self.check_fruit_in_private_message(message)
                    else:
                        # Get fruits first
                        await self.check_fruit_in_private_message(message)
                        click_delay = random.uniform(0.8, 3)
                        if rating < 1:
                            click_delay = random.uniform(4, 10)
                            
                        logging.info(f"Rating too low slow {click_delay}")
                        await self.click_card_button(message, best_index, click_delay)
                        self.dropped_cards_awaiting_pickup = False
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
            logging.debug("Got message from public drop")
            if len(message.attachments) <= 0:
                return
            components = message.components

            waited_for_edit = False

            if self.grab and not self.drop:
                if len(components) > 0:

                    logging.info(f"Analyzing message id={message.id} guild={message.channel.id}")

                    click_delay = random.uniform(0.55, 1.5)
                    rating = 0
                    best_index = random.randint(0, len(components)-1)
                    try:
                        best_index, rating = await self.get_best_card_index(message)
                    except Exception as e:
                        logging.error(f"OCR machine broke public {e}")
                        logging.error(traceback.format_exc())
                        return
                    click_delay = random.uniform(0.55, 1.5)

                    if best_index == -1:
                        logging.error(f"Could not process image for message: {message_content}")
                        return
                    
                    if rating >= 2:
                        logging.info(f" fast {click_delay}")
                        click_delay = random.uniform(0.4, 0.8)
                    if rating >= 5:
                        click_delay = random.uniform(0.2, 0.5)
                        logging.info(f"fastest {click_delay}")
                    try:
                        await self.wait_for("message_edit", check=check_for_message_button_edit, timeout=3)
                    except TimeoutError as e:
                        logging.error(f"Wait for timed out {e}")
                    waited_for_edit = True
                    logging.debug("Lets try to grab - drop is on cd")
                    if rating < 2:
                        logging.info("Rating too low, skipping")
                    else:
                        logging.info("Rating good, lets grab")
                        await self.click_card_button(message, best_index, click_delay)
                        await self.add_short_delay()
                else:
                    logging.error(f"No components in drop message, {message}")
            else:
                logging.debug(f"Cannot grab, on cd")

            if len(components) > 0:
                # Get fruits
                await self.check_fruit_in_public_message(message, waited_for_edit, check_for_message_button_edit)


    async def on_message_helper(self, message: discord.Message):

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

        # Message in channel
        message_content = message.content
        message_uuid = message.author.id
        try: 
            self.check_for_dm(message)
            self.check_fruit_grab(message_uuid, message_content)
            self.check_for_evasion(message_uuid, message_content)
            self.check_for_card_grab(message_uuid, message_content)
            self.check_for_cooldown_warning(message_uuid, message_content)
            await self.check_personal_drop(message_uuid, message_content, message, check_for_message_button_edit)
            self.check_for_generosity(message_uuid, message_content)
            await self.check_public_drop(message_uuid, message_content, message, check_for_message_button_edit)
        except Exception as e:
            logging.error(f"Something went wrong processing message {e}")

    async def get_best_card_index(self, message):
        start = time.time()

        processedImgResultList = []
        try:
            attachements_url = ""
            cardnum = extractNumCardsFromMessage(message.content)
            tempPath = f"temp/{message.id}"
            os.makedirs(tempPath, exist_ok = True)
            dropsPath = os.path.join(tempPath, "drops.webp")
            with open(dropsPath, "wb") as file:
                attachements_url = message.attachments[0].url
                file.write(requests.get(attachements_url).content)
            ocrPath = os.path.join(tempPath, "ocr")
            processedImgResultList = await preProcessImg(tempPath, dropsPath, ocrPath, cardnum)

        except Exception as e:
            logging.error(f"Something went wrong in processing, {e}, {attachements_url}")
        
        if len(processedImgResultList) == 0:
            return -1
        cardList = []
        for cardImageResult in processedImgResultList:

            seriesNameFromOcr = "--------------------------------"
            charNameFromOcr = "--------------------------------"
            try:            
                charNameFromOcr = ' '.join(reader.readtext(cardImageResult[0], detail=0))
                seriesOriginal = ' '.join(reader.readtext(cardImageResult[1], detail=0))
                seriesNameFromOcr = f"{seriesOriginal[:46]}..."
            except Exception as e:
                logging.error("Text OCR failure")
            UNKNOWN_PRINT_SENTINEL = 100000000
            printNumFromOcr = UNKNOWN_PRINT_SENTINEL
            try:
                ogReadPrint = reader.readtext(cardImageResult[2], detail=0, allowlist ='0123456789.')[0]
                printNumFromOcr = int(str.split(ogReadPrint,".")[0])
            except Exception as e:
                logging.error(f"print OCR failure for message {message.id}")

            cardList.append((charNameFromOcr, seriesNameFromOcr, printNumFromOcr ))
        logging.debug(f"Cardlist: {cardList}")

        # Query for the series/char.
        results = []
        
        for cardPos, (cardChar, cardSeries, cardPrint) in enumerate(cardList):
            found, matchedSeries, matchedChar, wishlistCount = findBestMatch(cardSeries, cardChar, self.seriesDB, self.characterDB)

            results.append(wishlistCount)
        logging.debug(f"Results: {results}")

        card_metadata = []

        for card, wishlist in zip(cardList, results):
            card_metadata.append({
                "name": card[0],
                "series": card[1],
                "printcount": card[2],
                "wlcount": wishlist
            })

        all_cards = []
        for og_index, meta in enumerate(card_metadata):
            all_cards.append((og_index, meta))

        high_wl = []
        mid_wl = []
        low_wl = []
        garbage_wl = []

        special_print = []
        great_print = []
        ok_print = []
        garbage_print = []

        for card in all_cards:
            wl = card[1]["wlcount"]
            print = card[1]["printcount"]

            if wl > 999:
                high_wl.append(card)
            if 999 >= wl > 50:
                mid_wl.append(card)
            if 50 >= wl > 19:
                low_wl.append(card)
            if 19 >= wl:
                garbage_wl.append(card)

            if UNKNOWN_PRINT_SENTINEL > print > 50000:
                garbage_print.append(card)
            if 50000 >= print >= 10000:
                ok_print.append(card)
            if 10000 > print:
                great_print.append(card)
            if print == UNKNOWN_PRINT_SENTINEL:
                special_print.append(card)

        # Sortem
        high_wl.sort(key=lambda x: x[1]["wlcount"], reverse=True)
        mid_wl.sort(key=lambda x: x[1]["wlcount"], reverse=True)
        low_wl.sort(key=lambda x: x[1]["wlcount"], reverse=True)
        garbage_wl.sort(key=lambda x: x[1]["wlcount"], reverse=True)

        special_print.sort(key=lambda x: x[1]["wlcount"], reverse=True)
        great_print.sort(key=lambda x: x[1]["wlcount"], reverse=True)
        ok_print.sort(key=lambda x: x[1]["wlcount"], reverse=True)
        garbage_print.sort(key=lambda x: x[1]["wlcount"], reverse=True)

        final_order = [] + high_wl + mid_wl + low_wl + special_print + great_print + ok_print + garbage_wl + garbage_print

        if len(final_order) == 0:
            final_order = all_cards

        logging.info(f"Cards analyzed:\n{"\n".join([
            f"{dec["name"] : <40}{dec["series"] : <40} WL: {dec["wlcount"] : <10} Print: {dec["printcount"]: <10}"
            for dec in card_metadata])}")
        
        rating = 0

        if (len(special_print) > 0):
            rating = 1
        if (len(low_wl) > 0):
            rating = 1
        if (len(mid_wl) > 0):
            rating = 2
        if (len(high_wl) > 0):
            rating = 10

        logging.info(f"rating {rating} final order: {str([val[0] for val in final_order])} ")

        end = time.time()
        logging.debug(f"Took {end-start} time to get best index")

        return final_order[0][0], rating


    
def run():
    client = MyClient()
    client.run(TOKEN)

if __name__ == "__main__":
    run()
