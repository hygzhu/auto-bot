import discord
import os
import logging
from rapidfuzz import process
from rapidfuzz import fuzz
from enum import Enum
from ocr import *
from wishlistdb import *
import time
import re


class DisplayStatus(Enum):
    PENDING = 1
    FOUND = 2
    MISSING = 3


class CardMessageType(Enum):
    ALL = 0
    HEARTS = 1
    HEARTSNUMBERS = 2
    NUMBERS = 3
    NAMES = 4


class ResultDisplay:
    def __init__(self):
        self.cardDropMessageType = CardMessageType.ALL
        self.title = ""
        self.footer = ""
        self.displayDelimiter = ""
        self.numcards = 0
        self.foundAny = False
        self.timeDisplay = 0
        self.startTime = 0
        self.dlTime = 0
        self.imageTime = 0
        self.ocrTime = 0
        self.queryTime = 0
        self.finishTime = 0
        self.displayList: list[str] = []
        self.displayStatus: list[DisplayStatus] = []

    # Resets and set all cards to pending
    # The first function called for card drop lookup messaging
    def setAsPending(self, cardNum, timeDisplay, msglvl) -> None:
        self.cardDropMessageType = msglvl
        self.numcards = cardNum
        self.timeDisplay = timeDisplay
        self.title = ""
        match msglvl:
            case CardMessageType.HEARTS.value:
                self.displayDelimiter = " "
            case CardMessageType.HEARTSNUMBERS.value:
                self.displayDelimiter = "    •    "
            case CardMessageType.NUMBERS.value:
                self.displayDelimiter = "    •    "
            case CardMessageType.NAMES.value:
                self.displayDelimiter = "\n"
            case _:
                self.displayDelimiter = "\n"
        for cardpos in range(0, cardNum):
            self.displayList.append(
                wishlistMessage(
                    cardpos + 1, "...", "...", "...", self.cardDropMessageType, 0
                )
            )
            self.displayStatus.append(DisplayStatus.PENDING)

    # Get the display string
    def getDisplay(self, printTiming=True) -> str:
        cardDisplay = f"{self.displayDelimiter.join(self.displayList)}\n"
        return "{}{}{}".format(self.title, cardDisplay, self.footer)

    def addFoundCard(
        self, cardpos: int, series: str, character: str, wishlistcount: int, print: int
    ):
        self.displayList[cardpos] = wishlistMessage(
            cardpos + 1,
            series,
            character,
            str(wishlistcount),
            self.cardDropMessageType,
            print,
        )
        self.displayStatus[cardpos] = DisplayStatus.FOUND
        self.foundAny = True

    def getMissingCardNum(self) -> list[int]:
        result = []
        for pos, status in enumerate(self.displayStatus):
            if status == DisplayStatus.PENDING:
                result.append(pos)
        return result

    def setPendingToMissing(self) -> bool:
        foundMissing = False
        for pos, status in enumerate(self.displayStatus):
            if status == DisplayStatus.PENDING:
                self.displayList[pos] = wishlistMessage(
                    pos + 1, "???", "???", "???", self.cardDropMessageType, 0
                )
                self.displayStatus[pos] = DisplayStatus.MISSING
                foundMissing = True
        return foundMissing


def paddedWLNum(wishlists):
    maxDigits = 5
    wishListString = wishlists.ljust(maxDigits)
    return wishListString


def wishlistMessage(cardpos, seriesname, charname, wishlists, level, cardprint):
    resultMsg = ""
    printTxt = printMsg(cardprint)
    heartEmote = heartEmoji(wishlists)

    # modified message
    match level:
        case CardMessageType.HEARTS.value:
            resultMsg = heartEmoji(wishlists)
        case CardMessageType.HEARTSNUMBERS.value:
            resultMsg = f"{printTxt}{heartEmote} `{paddedWLNum(wishlists)}`"
        case CardMessageType.NUMBERS.value:
            resultMsg = f"`{printTxt}{paddedWLNum(wishlists)}`"
        case CardMessageType.NAMES.value:
            resultMsg = f"`#{str(cardpos)}` • {heartEmote} `{paddedWLNum(wishlists)}` • **{charname}** {printTxt}"
        case _:
            resultMsg = f"`#{str(cardpos)}` • {heartEmote} `{paddedWLNum(wishlists)}` • **{charname}** • {seriesname} {printTxt}"

    return resultMsg


def printMsg(print: int):
    if print <= 0:
        return ""
    if print < 1000:
        return ":sparkles:"
    return ""


def getWishlistDataFromMessageEmbed(message):
    character_series_delimiter = "#~#"
    embed = message.embeds[0]
    wlLines = embed.fields[0].value.split("\n")
    dataToInsert = []
    for line in wlLines:
        data = line.split("♡")[1]
        dataList = data.split("·")
        wishlistcount = dataList[0].strip()[:-1]
        series = dataList[1].strip()
        character = dataList[2].strip()[2:][:-2]
        # print(character + " from " + series + " wl: " + wishlistcount)
        dataToInsert.append(
            (
                series,
                character,
                wishlistcount,
                series + character_series_delimiter + character,
            )
        )
    return dataToInsert


def getWishlistDataFromStarflightMessageEmbed(message):
    character_series_delimiter = "#~#"
    embed = message.embeds[0]
    wlLines = embed.description.split("\n")
    dataToInsert = []
    for line in wlLines:
        if not line.startswith("`#"):
            continue
        data = line.split("♡")[1]
        dataList = data.split("·")
        wishlistcount = dataList[0].strip()[:-1]
        character = dataList[1].strip()[2:][:-2]
        series = dataList[2].strip()
        # Trim series to use ... for those > 46 characters to match klu
        if len(series) > 46:
            series = f"{series[:46]}..."
        # print(character + " from " + series + " wl: " + wishlistcount)
        dataToInsert.append(
            (
                series,
                character,
                wishlistcount,
                series + character_series_delimiter + character,
            )
        )
    return dataToInsert


def checkKLFromKaruta(message):
    expectedTitle = "Character Results"
    if message.author.id != 646937666251915264:
        return False
    if len(message.embeds) <= 0:
        return False
    if message.embeds[0].title == None:
        print("Message embed has no title")
        return False
    if message.embeds[0].title.strip() != expectedTitle:
        # print("Message title "+message.embeds[0].title.strip()+" does not match "+expectedTitle)
        return False
    if message.reference == None:
        print("Message has no ref")
        return False
    if type(message.reference.resolved) != discord.Message:
        print("Message ref deleted or missing")
        return False
    if not message.reference.resolved.content.startswith("klu"):
        print("Message not klu")
        return False
    return True


def checkKLFromStarflight(message):
    expectedTitle = "Top WL characters in Karuta"
    if message.author.id != 816328822051045436:
        return False
    if len(message.embeds) <= 0:
        return False
    if message.embeds[0].author == None:
        print("Message embed has no author")
        return False
    if message.embeds[0].author.name == None:
        print("Message embed has no author name")
        return False
    if message.embeds[0].author.name.strip() != expectedTitle:
        # print(f"Message title {message.embeds[0].author.name.strip()} does not match {expectedTitle}")
        return False
    return True


def formatDecimal(float: float):
    return "{:.2f}".format(float)


# This returns the user ID given a ping format
# expected input is <@id>
def getUserIdFromPing(ping):
    header = ping[:2]
    if header != "<@":
        userid = ping[2:]
        return userid[:-1]
    else:
        return ping


# Process the drop image and return a list of (top, bot) paths for the top/bot crops as tuples
async def preProcessImg(
    saveFolderPath, imagePath, ocrPath, cardnum
) -> list[tuple[str, str]]:
    for a in range(cardnum):
        cardPath = os.path.join(saveFolderPath, f"card{a+1}.png")
        await get_card(cardPath, imagePath, a)

    os.makedirs(ocrPath, exist_ok=True)

    printPath = os.path.join(ocrPath, "print")
    topPath = os.path.join(ocrPath, "top")
    botPath = os.path.join(ocrPath, "bot")
    os.makedirs(printPath, exist_ok=True)
    os.makedirs(topPath, exist_ok=True)
    os.makedirs(botPath, exist_ok=True)

    cardPathList = []
    for a in range(cardnum):
        cardPath = os.path.join(saveFolderPath, f"card{a+1}.png")
        cardTopPath = os.path.join(topPath, f"top{a+1}.png")
        await get_top(cardPath, cardTopPath)
        cardBotPath = os.path.join(botPath, f"bot{a+1}.png")
        await get_bottom(cardPath, cardBotPath)
        cardPrintPath = os.path.join(printPath, f"print{a+1}.png")
        await get_print(cardPath, cardPrintPath)
        cardPathList.append((cardTopPath, cardBotPath, cardPrintPath))

    return cardPathList


def extractNumCardsFromMessage(message):
    withoutUser = str.split(message, "> ")
    latterHalf = withoutUser[len(withoutUser) - 1]
    number = ""
    try:
        if len(latterHalf) > 30:
            # This is a server drop
            number = latterHalf[13]
        else:
            # This is a user's drop
            number = latterHalf[12]
    except Exception as e:
        logging.error("Extract cards from message error, default to 3, :" + e)
        number = 3
    return int(number)


def heartEmoji(wishlistcount):
    if wishlistcount == "???" or wishlistcount == "...":
        return ":grey_heart:"
    count = int(wishlistcount)
    if count < 100:
        return ":grey_heart:"
    if count < 300:
        return ":yellow_heart:"
    if count < 600:
        return ":orange_heart:"
    if count < 1000:
        return ":heart:"
    if count < 3000:
        return ":sparkling_heart:"
    else:
        return ":heartpulse:"


# Process the drop image and return a list of (top, bot) paths for the top/bot crops as tuples
async def preProcessImg(
    saveFolderPath, imagePath, ocrPath, cardnum
) -> list[tuple[str, str]]:
    for a in range(cardnum):
        cardPath = os.path.join(saveFolderPath, f"card{a+1}.png")
        await get_card(cardPath, imagePath, a)

    os.makedirs(ocrPath, exist_ok=True)

    printPath = os.path.join(ocrPath, "print")
    topPath = os.path.join(ocrPath, "top")
    botPath = os.path.join(ocrPath, "bot")
    os.makedirs(printPath, exist_ok=True)
    os.makedirs(topPath, exist_ok=True)
    os.makedirs(botPath, exist_ok=True)

    cardPathList = []
    for a in range(cardnum):
        try:
            cardPath = os.path.join(saveFolderPath, f"card{a+1}.png")
            cardTopPath = os.path.join(topPath, f"top{a+1}.png")
            await get_top(cardPath, cardTopPath)
            cardBotPath = os.path.join(botPath, f"bot{a+1}.png")
            await get_bottom(cardPath, cardBotPath)
            cardPrintPath = os.path.join(printPath, f"print{a+1}.png")
            await get_print(cardPath, cardPrintPath)
            cardPathList.append((cardTopPath, cardBotPath, cardPrintPath))
        except:
            logging.error("Failed to get card path stuff")
    return cardPathList


# Finds the best match by series first, then character with >1 wishlists
# Returns found, matchedseries, matchedcharacter, wishlistcount
def findBestMatch(
    seriesToLookFor, charToLookFor, saved_seriesdb, saved_characterdb
) -> tuple[bool, str, str, int]:
    seriesBestMatch = process.extractOne(seriesToLookFor, saved_seriesdb)
    logging.debug("Best series match: " + str(seriesBestMatch))

    # check series name first and see if we can find a matching series
    if seriesBestMatch[1] >= 70:
        matchedSeries = seriesBestMatch[0]
        characterDB = queryWishList(
            "SELECT DISTINCT character FROM cardinfo WHERE series LIKE ? ORDER BY wishlistcount desc, series asc, character asc",
            (f"%{matchedSeries}%",),
        )

        # then see if we can find a matching character from that series
        charBestMatch = process.extractOne(charToLookFor, characterDB)
        logging.debug("Best Series Match >= 70, Best char match: " + str(charBestMatch))

        # if the character is also close enough, that works
        if charBestMatch[1] >= 70 or (
            seriesBestMatch[1] >= 90 and charBestMatch[1] >= 65
        ):
            matchedChar = charBestMatch[0]
            queryResult = queryWishList(
                "SELECT DISTINCT wishlistcount FROM cardinfo WHERE series = ? and character = ? ORDER BY wishlistcount desc, series asc, character asc",
                (
                    matchedSeries,
                    matchedChar,
                ),
            )
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
    charBestMatch = process.extractOne(charToLookFor, saved_characterdb)
    logging.debug("Best char match: " + str(charBestMatch))

    if charBestMatch[1] >= 90:
        matchedChar = charBestMatch[0]
        seriesDB = queryWishList(
            "SELECT DISTINCT series FROM cardinfo WHERE character = ? ORDER BY wishlistcount desc, series asc, character asc",
            (matchedChar,),
        )
        seriesBestMatchNarrowed = process.extractOne(seriesToLookFor, seriesDB)
        logging.debug(
            "Best Char Match >= 90, Best series match: " + str(seriesBestMatchNarrowed)
        )

        if seriesBestMatchNarrowed[1] >= 65:
            matchedSeries = seriesBestMatchNarrowed[0]
            queryResult = queryWishList(
                "SELECT DISTINCT wishlistcount FROM cardinfo WHERE series = ? and character = ? ORDER BY wishlistcount desc, series asc, character asc",
                (
                    matchedSeries,
                    matchedChar,
                ),
            )
            if len(queryResult) > 0:
                wishlistcount = queryResult[0]
                logging.debug("Best match: " + matchedChar + " from " + matchedSeries)
                return (True, matchedSeries, matchedChar, wishlistcount)
    return (False, "", "", -1)


def is_hour_between(start, end, now):
    is_between = False

    is_between |= start <= now <= end
    is_between |= end < start and (start <= now or now <= end)

    return is_between


def get_kjb_dict(message: discord.Message, user_id):
    if (
        len(message.embeds) > 0
        and message.embeds[0].description
        and f"Showing board of <@{user_id}>" in message.embeds[0].description
    ):
        contribution = message.embeds[0].description
        # Create an empty dictionary to store the mappings
        contribution_dict = {}

        # Use a regular expression to find each line with the data we need
        pattern = r"🇦|🇧|🇨|🇩|🇪"
        matches = re.findall(
            r"(🇦|🇧|🇨|🇩|🇪) (.+?) · \*\*(\d+)\*\* Effort · `(.*?)`", contribution
        )

        # Alphabet letters mapping to the respective emoji flag
        letter_mapping = {"🇦": "a", "🇧": "b", "🇨": "c", "🇩": "d", "🇪": "e"}

        for letter, name, effort, status in matches:

            # Hack for alias
            if name == "Miyuki Shirogane":
                name = "Prez"

            letter_key = letter_mapping[letter]
            contribution_dict[letter_key] = (name, int(effort), status)

        # {'a': ('Erwin Smith', '176', 'Healthy'), 'b': ('Blanc', '174', 'Healthy'), 'c': ('Sanma', '166', 'Healthy'), 'd': ('Altiria Ray O’ltriese', '141', 'Healthy'), 'e': ('Parsee Mizuhashi', '114', 'Healthy')}
        return contribution_dict
    return {}


def get_kc_effort_list(message: discord.Message, user_id):
    if (
        len(message.embeds) > 0
        and message.embeds[0].description
        and f"Cards owned by <@{user_id}>" in message.embeds[0].description
    ):
        inpuit_string = message.embeds[0].description
        # Regular expression pattern to match the desired information
        pattern = r"\`✧(\d+)\`\s·\s\*\*`([^`]+)`\*\*\s·.*?·\s\*\*(.*?)\*\*"

        # Find all matches
        matches = re.findall(pattern, inpuit_string)

        # Convert the matches to the required format
        result = [(int(score), id_, name) for score, id_, name in matches]
        # [
        #     (190, "v1b72qv", "Minato Namikaze"),
        #     (180, "v11qzpf", "Itsuki Nakano"),
        #     (176, "v1vnqb6", "Erwin Smith"),
        #     (174, "v10hs1p", "Blanc"),
        #     (168, "v1brw4m", "Amako"),
        #     (166, "v1vdg5d", "Sanma"),
        #     (156, "v12gz2r", "Yuzu Izumi"),
        #     (141, "v108qm3", "Altiria Ray O’ltriese"),
        #     (114, "v10mhn3", "Parsee Mizuhashi"),
        #     (109, "vnxh4w4", "Ripple"),
        # ]

        return result
    return []


def get_tax_values(message: discord.Message):
    if (
        len(message.embeds) > 0
        and message.embeds[0].title
        and "Nodes Overview" in message.embeds[0].title
    ):
        inputstring = message.embeds[0].description
        # Regex pattern to match material name and tax percentage
        pattern = r"`(\w+)` · \*\*(\d+)%\*\* tax"

        # Find all matches
        matches = re.findall(pattern, inputstring)

        # Convert matches into the required list of tuples
        result = [(int(tax), name) for name, tax in matches]
        # [(50, 'gold'), (10, 'salt'), (10, 'oil'), (10, 'magma'), (10, 'iron'), (10, 'ice'), (10, 'flower'), (10, 'essence'), (10, 'copper'), (10, 'clay')]
        return result
    return []
