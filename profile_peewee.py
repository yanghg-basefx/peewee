import cProfile
import datetime
import functools
import glob
import optparse
import os
import pstats

from peewee import *

from playhouse.sqlite_ext import SqliteExtDatabase

db = SqliteDatabase(':memory:')
#db = SqliteExtDatabase(':memory:', c_extensions=True)

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    username = CharField(unique=True)

class Tweet(BaseModel):
    user = ForeignKeyField(User, related_name='tweets')
    content = TextField(default='')
    timestamp = DateTimeField(default=datetime.datetime.now)

def create(n):
    for i in range(n):
        user = User.create(username='user-%s' % i)
        Tweet.create(user=user)

SAVE_STATS = True

def profile(filename):
    def decorator(fn):
        profiler = cProfile.Profile()
        @functools.wraps(fn)
        def inner(*args, **kwargs):
            profiler.runcall(fn, *args, **kwargs)
            if SAVE_STATS:
                profiler.dump_stats(filename)
        return inner
    return decorator

@profile('insert.stats')
def insert(num):
    create(num)

@profile('update.stats')
def update(num):
    for idx in range(num):
        (User
         .update(username=fn.UPPER(User.username))
         .where(User.username == 'user-%s' % idx)
         .execute())

@profile('select.stats')
def select():
    for user in User.select():
        pass

@profile('tuples.stats')
def tuples():
    for user in User.select().tuples():
        pass

@profile('dicts.stats')
def dicts():
    for user in User.select().dicts():
        pass

@profile('get.stats')
def select_get(num):
    for idx in range(num):
        User.get(User.username == 'user-%s' % idx)

@profile('joins.stats')
def joins():
    query = (Tweet
             .select(Tweet, User)
             .join(User))
    for tweet in query:
        x = tweet.user.username

@profile('join_agg.stats')
def join_agg():
    query = (User
             .select(User, Tweet)
             .join(Tweet, JOIN_LEFT_OUTER)
             .aggregate_rows())
    for user in query:
        pass

@profile('prefetch.stats')
def prefetch_prof():
    query = prefetch(User.select(), Tweet.select())
    for user in query:
        pass

@profile('delete.stats')
def delete(num):
    for tweet in Tweet.select():
        tweet.delete_instance(recursive=True)

def get_option_parser():
    parser = optparse.OptionParser()
    def add_option(dest, key=None):
        if key is None:
            key = dest[0]
        parser.add_option(
            '-%s' % key,
            '--%s' % dest,
            action='store_true',
            dest=dest)
    add_option('select')
    add_option('tuples', 'z')
    add_option('dicts', 'x')
    add_option('get')
    add_option('joins')
    add_option('join_agg', 'w')
    add_option('prefetch', 'f')
    add_option('insert')
    add_option('update')
    add_option('delete')
    add_option('save', 'o')
    add_option('all')
    parser.add_option(
        '-p',
        '--print',
        action='store_true',
        dest='print_stats')
    parser.add_option(
        '--sorting',
        default='cumtime',
        dest='sorting')
    parser.add_option(
        '-n',
        '--number',
        default=1000,
        dest='number',
        type='int')
    return parser

if __name__ == '__main__':
    parser = get_option_parser()
    options, args = parser.parse_args()
    num = options.number

    db.create_tables([User, Tweet])
    if options.insert or options.all:
        insert(num)
    else:
        create(num)  # Make sure we have some rows to work with.

    if options.update or options.all:
        update(num)
        User.delete().execute()
        create(num)

    if options.select or options.all:
        select()
    if options.tuples or options.all:
        tuples()
    if options.dicts or options.all:
        dicts()
    if options.get or options.all:
        select_get(num)
    if options.joins or options.all:
        joins()
    if options.join_agg or options.all:
        join_agg()
    if options.prefetch or options.all:
        prefetch_prof()
    if options.delete or options.all:
        delete(num)

    if options.print_stats:
        filenames = glob.glob('*.stats')
        for filename in sorted(filenames):
            print filename + '\n' + '=' * len(filename)
            stats = pstats.Stats(filename)
            stats.sort_stats(options.sorting).print_stats(75)
            print '\n\n' + ('-' * 79) + '\n\n'

    if not options.save:
        filenames = glob.glob('*.stats')
        for filename in sorted(filenames):
            os.unlink(filename)
