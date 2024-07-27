import sqlite3

DB_NAME = "karutawishlists.db"

class Wishlist:
    # vulnerable to sql injection btw
    def __init__(self):
        self.db = sqlite3.connect(DB_NAME)
        self.db.execute('create table if not exists characterwishlist ( userId varchar(255), name varchar(255))')
        self.db.execute('create table if not exists serieswishlist ( userId varchar(255), name varchar(255))')

    def get_wishlist_chars(self, userId: str) -> list[str]:
        data = (userId,)
        res = self.db.execute(f"select name from characterwishlist where userId = ?", data)
        characters = res.fetchall()
        char_list = [char[0] for char in characters]
        return char_list

    def get_wishlist_series(self, userId: str) -> list[str]:
        data = (userId,)
        res = self.db.execute(f"select name from serieswishlist where userId = ?", data)
        serieslist = res.fetchall()
        series_list =[series[0] for series in serieslist]
        return series_list

    def get_all_char_wishlist_items(self):
        res = self.db.execute(f"select name from characterwishlist")
        characters = res.fetchall()
        return [char[0] for char in characters] 


    def get_all_series_wishlist_items(self):
        res = self.db.execute(f"select name from serieswishlist")
        serieslist = res.fetchall()
        return [series[0] for series in serieslist]


    def add_character_to_wishlist(self, userId: str, character: str) -> None:
        data = (userId, character)
        self.db.execute('insert into characterwishlist values (?, ?)', data)
        self.db.commit()

    def add_series_to_wishlist(self, userId: str, series: str) -> None:
        data = (userId, series)
        self.db.execute('insert into serieswishlist values (?, ?)', data)
        self.db.commit()

    def remove_character_from_wishlist(self, userId: str, character: str) -> None:
        data = (userId, character)
        self.db.execute('delete from characterwishlist where userId=? and name=?', data)
        self.db.commit()

    def remove_series_from_wishlist(self, userId: str, series: str) -> None:
        data = (userId, series)
        self.db.execute('delete from serieswishlist where userId=? and name=?', data)
        self.db.commit()

# The result is flattened, i.e only the first result of the tuple is returned!
def queryWishList(sql, params = ()):
    con = sqlite3.connect(DB_NAME)
    con.row_factory = lambda cursor, row: row[0]
    cur = con.cursor()
    res = cur.execute(sql, params)
    return res.fetchall()

def insertWishList(data):
    con = sqlite3.connect(DB_NAME)
    cur = con.cursor()
    cur.executemany("INSERT INTO cardinfo VALUES(?, ?, ?, ?) ON CONFLICT(seriescharacter) DO UPDATE SET wishlistcount=excluded.wishlistcount", data)
    con.commit()  # Remember to commit the transaction after executing INSERT.