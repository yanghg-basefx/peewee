import datetime

from peewee import *

from .base import BaseTestCase
from .base import IS_MYSQL
from .base import IS_MYSQL_ADVANCED_FEATURES
from .base import IS_SQLITE_OLD
from .base import ModelTestCase
from .base import TestModel
from .base import get_in_memory_db
from .base import requires_models
from .base import requires_mysql
from .base import requires_postgresql
from .base import skip_if
from .base_models import Sample
from .base_models import Tweet
from .base_models import User


class ColAlias(TestModel):
    name = TextField(column_name='pname')


class CARef(TestModel):
    colalias = ForeignKeyField(ColAlias, backref='carefs', column_name='ca',
                               object_id_name='colalias_id')


class TestQueryAliasToColumnName(ModelTestCase):
    requires = [ColAlias, CARef]

    def setUp(self):
        super(TestQueryAliasToColumnName, self).setUp()
        with self.database.atomic():
            for name in ('huey', 'mickey'):
                col_alias = ColAlias.create(name=name)
                CARef.create(colalias=col_alias)

    def test_alias_to_column_name(self):
        # The issue here occurs when we take a field whose name differs from
        # it's underlying column name, then alias that field to it's column
        # name. In this case, peewee was *not* respecting the alias and using
        # the field name instead.
        query = (ColAlias
                 .select(ColAlias.name.alias('pname'))
                 .order_by(ColAlias.name))
        self.assertEqual([c.pname for c in query], ['huey', 'mickey'])

        # Ensure that when using dicts the logic is preserved.
        query = query.dicts()
        self.assertEqual([r['pname'] for r in query], ['huey', 'mickey'])

    def test_alias_overlap_with_join(self):
        query = (CARef
                 .select(CARef, ColAlias.name.alias('pname'))
                 .join(ColAlias)
                 .order_by(ColAlias.name))
        with self.assertQueryCount(1):
            self.assertEqual([r.colalias.pname for r in query],
                             ['huey', 'mickey'])

        # Note: we cannot alias the join to "ca", as this is the object-id
        # descriptor name.
        query = (CARef
                 .select(CARef, ColAlias.name.alias('pname'))
                 .join(ColAlias,
                       on=(CARef.colalias == ColAlias.id).alias('ca'))
                 .order_by(ColAlias.name))
        with self.assertQueryCount(1):
            self.assertEqual([r.ca.pname for r in query], ['huey', 'mickey'])

    def test_cannot_alias_join_to_object_id_name(self):
        query = CARef.select(CARef, ColAlias.name.alias('pname'))
        expr = (CARef.colalias == ColAlias.id).alias('colalias_id')
        self.assertRaises(ValueError, query.join, ColAlias, on=expr)


class TestOverrideModelRepr(BaseTestCase):
    def test_custom_reprs(self):
        # In 3.5.0, Peewee included a new implementation and semantics for
        # customizing model reprs. This introduced a regression where model
        # classes that defined a __repr__() method had this override ignored
        # silently. This test ensures that it is possible to completely
        # override the model repr.
        class Foo(Model):
            def __repr__(self):
                return 'FOO: %s' % self.id

        f = Foo(id=1337)
        self.assertEqual(repr(f), 'FOO: 1337')


class DiA(TestModel):
    a = TextField(unique=True)
class DiB(TestModel):
    a = ForeignKeyField(DiA)
    b = TextField()
class DiC(TestModel):
    b = ForeignKeyField(DiB)
    c = TextField()
class DiD(TestModel):
    c = ForeignKeyField(DiC)
    d = TextField()
class DiBA(TestModel):
    a = ForeignKeyField(DiA, to_field=DiA.a)
    b = TextField()


class TestDeleteInstanceRegression(ModelTestCase):
    database = get_in_memory_db()
    requires = [DiA, DiB, DiC, DiD, DiBA]

    def test_delete_instance_regression(self):
        with self.database.atomic():
            a1, a2, a3 = [DiA.create(a=a) for a in ('a1', 'a2', 'a3')]
            for a in (a1, a2, a3):
                for j in (1, 2):
                    b = DiB.create(a=a, b='%s-b%s' % (a.a, j))
                    c = DiC.create(b=b, c='%s-c' % (b.b))
                    d = DiD.create(c=c, d='%s-d' % (c.c))

                    DiBA.create(a=a, b='%s-b%s' % (a.a, j))

        # (a1 (b1 (c (d))), (b2 (c (d)))), (a2 ...), (a3 ...)
        with self.assertQueryCount(5):
            a2.delete_instance(recursive=True)

        queries = [logrecord.msg for logrecord in self._qh.queries[-5:]]
        self.assertEqual(sorted(queries, reverse=True), [
            ('DELETE FROM "di_d" WHERE ("di_d"."c_id" IN ('
             'SELECT "t1"."id" FROM "di_c" AS "t1" WHERE ("t1"."b_id" IN ('
             'SELECT "t2"."id" FROM "di_b" AS "t2" WHERE ("t2"."a_id" = ?)'
             '))))', [2]),
            ('DELETE FROM "di_c" WHERE ("di_c"."b_id" IN ('
             'SELECT "t1"."id" FROM "di_b" AS "t1" WHERE ("t1"."a_id" = ?)'
             '))', [2]),
            ('DELETE FROM "di_ba" WHERE ("di_ba"."a_id" = ?)', ['a2']),
            ('DELETE FROM "di_b" WHERE ("di_b"."a_id" = ?)', [2]),
            ('DELETE FROM "di_a" WHERE ("di_a"."id" = ?)', [2])
        ])

        # a1 & a3 exist, plus their relations.
        self.assertTrue(DiA.select().count(), 2)
        for rel in (DiB, DiBA, DiC, DiD):
            self.assertTrue(rel.select().count(), 4)  # 2x2

        with self.assertQueryCount(5):
            a1.delete_instance(recursive=True)

        # Only the objects related to a3 exist still.
        self.assertTrue(DiA.select().count(), 1)
        self.assertEqual(DiA.get(DiA.a == 'a3').id, a3.id)
        self.assertEqual([d.d for d in DiD.select().order_by(DiD.d)],
                         ['a3-b1-c-d', 'a3-b2-c-d'])
        self.assertEqual([c.c for c in DiC.select().order_by(DiC.c)],
                         ['a3-b1-c', 'a3-b2-c'])
        self.assertEqual([b.b for b in DiB.select().order_by(DiB.b)],
                         ['a3-b1', 'a3-b2'])
        self.assertEqual([ba.b for ba in DiBA.select().order_by(DiBA.b)],
                         ['a3-b1', 'a3-b2'])


class TestCountUnionRegression(ModelTestCase):
    @requires_mysql
    @requires_models(User)
    def test_count_union(self):
        with self.database.atomic():
            for i in range(5):
                User.create(username='user-%d' % i)

        lhs = User.select()
        rhs = User.select()
        query = (lhs | rhs)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'UNION '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2"'), [])

        self.assertEqual(query.count(), 5)

        query = query.limit(3)
        self.assertSQL(query, (
            'SELECT "t1"."id", "t1"."username" FROM "users" AS "t1" '
            'UNION '
            'SELECT "t2"."id", "t2"."username" FROM "users" AS "t2" '
            'LIMIT ?'), [3])
        self.assertEqual(query.count(), 3)


class User2(TestModel):
    username = TextField()

class Category2(TestModel):
    name = TextField()
    parent = ForeignKeyField('self', backref='children', null=True)
    user = ForeignKeyField(User2)


class TestGithub1354(ModelTestCase):
    @requires_models(Category2, User2)
    def test_get_or_create_self_referential_fk2(self):
        huey = User2.create(username='huey')
        parent = Category2.create(name='parent', user=huey)
        child, created = Category2.get_or_create(parent=parent, name='child',
                                                 user=huey)
        child_db = Category2.get(Category2.parent == parent)
        self.assertEqual(child_db.user.username, 'huey')
        self.assertEqual(child_db.parent.name, 'parent')
        self.assertEqual(child_db.name, 'child')


class TestInsertFromSQL(ModelTestCase):
    def setUp(self):
        super(TestInsertFromSQL, self).setUp()

        self.database.execute_sql('create table if not exists user_src '
                                  '(name TEXT);')
        tbl = Table('user_src').bind(self.database)
        tbl.insert(name='foo').execute()

    def tearDown(self):
        super(TestInsertFromSQL, self).tearDown()
        self.database.execute_sql('drop table if exists user_src')

    @requires_models(User)
    def test_insert_from_sql(self):
        query_src = SQL('SELECT name FROM user_src')
        User.insert_from(query=query_src, fields=[User.username]).execute()
        self.assertEqual([u.username for u in User.select()], ['foo'])


class TestSubqueryFunctionCall(BaseTestCase):
    def test_subquery_function_call(self):
        Sample = Table('sample')
        SA = Sample.alias('s2')
        query = (Sample
                 .select(Sample.c.data)
                 .where(~fn.EXISTS(
                     SA.select(SQL('1')).where(SA.c.key == 'foo'))))
        self.assertSQL(query, (
            'SELECT "t1"."data" FROM "sample" AS "t1" '
            'WHERE NOT EXISTS('
            'SELECT 1 FROM "sample" AS "s2" WHERE ("s2"."key" = ?))'), ['foo'])


class A(TestModel):
    id = IntegerField(primary_key=True)
class B(TestModel):
    id = IntegerField(primary_key=True)
class C(TestModel):
    id = IntegerField(primary_key=True)
    a = ForeignKeyField(A)
    b = ForeignKeyField(B)

class TestCrossJoin(ModelTestCase):
    requires = [A, B, C]

    def setUp(self):
        super(TestCrossJoin, self).setUp()
        A.insert_many([(1,), (2,), (3,)], fields=[A.id]).execute()
        B.insert_many([(1,), (2,)], fields=[B.id]).execute()
        C.insert_many([
            (1, 1, 1),
            (2, 1, 2),
            (3, 2, 1)], fields=[C.id, C.a, C.b]).execute()

    def test_cross_join(self):
        query = (A
                 .select(A.id.alias('aid'), B.id.alias('bid'))
                 .join(B, JOIN.CROSS)
                 .join(C, JOIN.LEFT_OUTER, on=(
                     (C.a == A.id) &
                     (C.b == B.id)))
                 .where(C.id.is_null())
                 .order_by(A.id, B.id))
        self.assertEqual(list(query.tuples()), [(2, 2), (3, 1), (3, 2)])


def _create_users_tweets(db):
    data = (
        ('huey', ('meow', 'hiss', 'purr')),
        ('mickey', ('woof', 'bark')),
        ('zaizee', ()))
    with db.atomic():
        for username, tweets in data:
            user = User.create(username=username)
            for tweet in tweets:
                Tweet.create(user=user, content=tweet)


class TestSubqueryInSelect(ModelTestCase):
    requires = [User, Tweet]

    def setUp(self):
        super(TestSubqueryInSelect, self).setUp()
        _create_users_tweets(self.database)

    def test_subquery_in_select(self):
        subq = User.select().where(User.username == 'huey')
        query = (Tweet
                 .select(Tweet.content, Tweet.user.in_(subq).alias('is_huey'))
                 .order_by(Tweet.content))
        self.assertEqual([(r.content, r.is_huey) for r in query], [
            ('bark', False),
            ('hiss', True),
            ('meow', True),
            ('purr', True),
            ('woof', False)])


@requires_postgresql
class TestReturningIntegrationRegressions(ModelTestCase):
    requires = [User, Tweet]

    def test_returning_integration_subqueries(self):
        _create_users_tweets(self.database)

        # We can use a correlated subquery in the RETURNING clause.
        subq = (Tweet
                .select(fn.COUNT(Tweet.id).alias('ct'))
                .where(Tweet.user == User.id))
        query = (User
                 .update(username=(User.username + '-x'))
                 .returning(subq, User.username))
        result = query.execute()
        self.assertEqual(sorted([(r.ct, r.username) for r in result]), [
            (0, 'zaizee-x'), (2, 'mickey-x'), (3, 'huey-x')])

        # We can use a correlated subquery via UPDATE...FROM, and reference the
        # FROM table in both the update and the RETURNING clause.
        subq = (User
                .select(User.id, fn.COUNT(Tweet.id).alias('ct'))
                .join(Tweet, JOIN.LEFT_OUTER)
                .group_by(User.id))
        query = (User
                 .update(username=User.username + subq.c.ct)
                 .from_(subq)
                 .where(User.id == subq.c.id)
                 .returning(subq.c.ct, User.username))
        result = query.execute()
        self.assertEqual(sorted([(r.ct, r.username) for r in result]), [
            (0, 'zaizee-x0'), (2, 'mickey-x2'), (3, 'huey-x3')])

    def test_returning_integration(self):
        query = (User
                 .insert_many([('huey',), ('mickey',), ('zaizee',)],
                              fields=[User.username])
                 .returning(User.id, User.username)
                 .objects())
        result = query.execute()
        self.assertEqual([(r.id, r.username) for r in result], [
            (1, 'huey'), (2, 'mickey'), (3, 'zaizee')])

        query = (User
                 .delete()
                 .where(~User.username.startswith('h'))
                 .returning(User.id, User.username)
                 .objects())
        result = query.execute()
        self.assertEqual(sorted([(r.id, r.username) for r in result]), [
            (2, 'mickey'), (3, 'zaizee')])


class TestUpdateIntegrationRegressions(ModelTestCase):
    requires = [User, Tweet, Sample]

    def setUp(self):
        super(TestUpdateIntegrationRegressions, self).setUp()
        _create_users_tweets(self.database)
        for i in range(4):
            Sample.create(counter=i, value=i)

    @skip_if(IS_MYSQL)
    def test_update_examples(self):
        # Do a simple update.
        res = (User
               .update(username=(User.username + '-cat'))
               .where(User.username != 'mickey')
               .execute())

        users = User.select().order_by(User.username)
        self.assertEqual([u.username for u in users.clone()],
                         ['huey-cat', 'mickey', 'zaizee-cat'])

        # Do an update using a subquery..
        subq = User.select(User.username).where(User.username == 'mickey')
        res = (User
               .update(username=(User.username + '-dog'))
               .where(User.username.in_(subq))
               .execute())
        self.assertEqual([u.username for u in users.clone()],
                         ['huey-cat', 'mickey-dog', 'zaizee-cat'])

        # Subquery referring to a different table.
        subq = User.select().where(User.username == 'mickey-dog')
        res = (Tweet
               .update(content=(Tweet.content + '-x'))
               .where(Tweet.user.in_(subq))
               .execute())

        self.assertEqual(
            [t.content for t in Tweet.select().order_by(Tweet.id)],
            ['meow', 'hiss', 'purr', 'woof-x', 'bark-x'])

        # Subquery on the right-hand of the assignment.
        subq = Tweet.select(fn.COUNT(Tweet.id)).where(Tweet.user == User.id)
        res = User.update(username=(User.username + '-' + subq)).execute()

        self.assertEqual([u.username for u in users.clone()],
                         ['huey-cat-3', 'mickey-dog-2', 'zaizee-cat-0'])

    def test_update_examples_2(self):
        SA = Sample.alias()
        subq = (SA
                .select(SA.value)
                .where(SA.value.in_([1.0, 3.0])))
        res = (Sample
               .update(counter=(Sample.counter + Sample.value))
               .where(Sample.value.in_(subq))
               .execute())

        query = (Sample
                 .select(Sample.counter, Sample.value)
                 .order_by(Sample.id)
                 .tuples())
        self.assertEqual(list(query.clone()), [(0, 0.), (2, 1.), (2, 2.),
                                               (6, 3.)])

        subq = SA.select(SA.counter - SA.value).where(SA.value == Sample.value)
        res = (Sample
               .update(counter=subq)
               .where(Sample.value.in_([1., 3.]))
               .execute())
        self.assertEqual(list(query.clone()), [(0, 0.), (1, 1.), (2, 2.),
                                               (3, 3.)])

class TestSelectValueConversion(ModelTestCase):
    requires = [User]

    @skip_if(IS_SQLITE_OLD or IS_MYSQL)
    def test_select_value_conversion(self):
        u1 = User.create(username='u1')
        cte = User.select(User.id.cast('text')).cte('tmp', columns=('id',))

        query = User.select(cte.c.id.alias('id')).with_cte(cte).from_(cte)
        u1_id, = [user.id for user in query]
        self.assertEqual(u1_id, u1.id)

        query2 = User.select(cte.c.id.coerce(False)).with_cte(cte).from_(cte)
        u1_id, = [user.id for user in query2]
        self.assertEqual(u1_id, str(u1.id))


class ConflictDetectedException(Exception): pass

class BaseVersionedModel(TestModel):
    version = IntegerField(default=1, index=True)

    def save_optimistic(self):
        if not self.id:
            # This is a new record, so the default logic is to perform an
            # INSERT. Ideally your model would also have a unique
            # constraint that made it impossible for two INSERTs to happen
            # at the same time.
            return self.save()

        # Update any data that has changed and bump the version counter.
        field_data = dict(self.__data__)
        current_version = field_data.pop('version', 1)
        self._populate_unsaved_relations(field_data)
        field_data = self._prune_fields(field_data, self.dirty_fields)
        if not field_data:
            raise ValueError('No changes have been made.')

        ModelClass = type(self)
        field_data['version'] = ModelClass.version + 1  # Atomic increment.

        query = ModelClass.update(**field_data).where(
            (ModelClass.version == current_version) &
            (ModelClass.id == self.id))
        if query.execute() == 0:
            # No rows were updated, indicating another process has saved
            # a new version. How you handle this situation is up to you,
            # but for simplicity I'm just raising an exception.
            raise ConflictDetectedException()
        else:
            # Increment local version to match what is now in the db.
            self.version += 1
            return True

class VUser(BaseVersionedModel):
    username = TextField()

class VTweet(BaseVersionedModel):
    user = ForeignKeyField(VUser, null=True)
    content = TextField()


class TestOptimisticLockingDemo(ModelTestCase):
    requires = [VUser, VTweet]

    def test_optimistic_locking(self):
        vu = VUser(username='u1')
        vu.save_optimistic()
        vt = VTweet(user=vu, content='t1')
        vt.save_optimistic()

        # Update the "vt" row in the db, which bumps the version counter.
        vt2 = VTweet.get(VTweet.id == vt.id)
        vt2.content = 't1-x'
        vt2.save_optimistic()

        # Since no data was modified, this returns a ValueError.
        self.assertRaises(ValueError, vt.save_optimistic)

        # If we do make an update and attempt to save, a conflict is detected.
        vt.content = 't1-y'
        self.assertRaises(ConflictDetectedException, vt.save_optimistic)
        self.assertEqual(vt.version, 1)

        vt_db = VTweet.get(VTweet.id == vt.id)
        self.assertEqual(vt_db.content, 't1-x')
        self.assertEqual(vt_db.version, 2)
        self.assertEqual(vt_db.user.username, 'u1')

    def test_optimistic_locking_populate_fks(self):
        vt = VTweet(content='t1')
        vt.save_optimistic()

        vu = VUser(username='u1')
        vt.user = vu

        vu.save_optimistic()
        vt.save_optimistic()
        vt_db = VTweet.get(VTweet.content == 't1')
        self.assertEqual(vt_db.version, 2)
        self.assertEqual(vt_db.user.username, 'u1')


class TS(TestModel):
    key = CharField(primary_key=True)
    timestamp = TimestampField(utc=True)


class TestZeroTimestamp(ModelTestCase):
    requires = [TS]

    def test_zero_timestamp(self):
        t0 = TS.create(key='t0', timestamp=0)
        t1 = TS.create(key='t1', timestamp=1)

        t0_db = TS.get(TS.key == 't0')
        self.assertEqual(t0_db.timestamp, datetime.datetime(1970, 1, 1))

        t1_db = TS.get(TS.key == 't1')
        self.assertEqual(t1_db.timestamp,
                         datetime.datetime(1970, 1, 1, 0, 0, 1))


class Player(TestModel):
    name = TextField()

class Game(TestModel):
    name = TextField()
    player = ForeignKeyField(Player)

class Score(TestModel):
    game = ForeignKeyField(Game)
    points = IntegerField()


class TestJoinSubqueryAggregateViaLeftOuter(ModelTestCase):
    requires = [Player, Game, Score]

    def test_join_subquery_aggregate_left_outer(self):
        with self.database.atomic():
            p1, p2 = [Player.create(name=name) for name in ('p1', 'p2')]
            games = []
            for p in (p1, p2):
                for gnum in (1, 2):
                    g = Game.create(name='%s-g%s' % (p.name, gnum), player=p)
                    games.append(g)

            score_list = (
                (10, 20, 30),
                (),
                (100, 110, 100),
                (50, 50))
            for g, plist in zip(games, score_list):
                for p in plist:
                    Score.create(game=g, points=p)

        subq = (Game
                .select(Game.player, fn.SUM(Score.points).alias('ptotal'),
                        fn.AVG(Score.points).alias('pavg'))
                .join(Score, JOIN.LEFT_OUTER)
                .group_by(Game.player))
        query = (Player
                 .select(Player, subq.c.ptotal, subq.c.pavg)
                 .join(subq, on=(Player.id == subq.c.player_id))
                 .order_by(Player.name))

        with self.assertQueryCount(1):
            results = [(p.name, p.game.ptotal, p.game.pavg) for p in query]

        self.assertEqual(results, [('p1', 60, 20), ('p2', 410, 82)])

        with self.assertQueryCount(1):
            obj_query = query.objects()
            results = [(p.name, p.ptotal, p.pavg) for p in obj_query]

        self.assertEqual(results, [('p1', 60, 20), ('p2', 410, 82)])
