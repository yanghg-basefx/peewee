.. _overview:

Overview
========

This document provides a broad overview of the many topics that are addressed
in detail in subsequent sections. It's purpose is to provide an introduction to
the APIs provided by Peewee.

Database Configuration
----------------------

A good first step when setting up an application with Peewee is to set up the
:py:class:`Database`. Out-of-the-box, Peewee supports:

* SQLite
  * :py:class:`SqliteDatabase`
  * :py:class:`SqliteExtDatabase` - supports additional SQLite-specific
    functionality, such as: full-text search support, true auto-incrementing
    primary keys, JSON1 extension support, etc.
  * :py:class:`PooledSqliteDatabase` - adds connection pooling to SQLite.
  * :py:class:`PooledSqliteExtDatabase`
  * :py:class:`APSWDatabase` - uses the 3rd-party SQLite driver :ref:`APSW
    <https://github.com/rogerbinns/apsw` instead of :ref:`pysqlite
    <https://github.com/ghaering/pysqlite`.
* MySQL
  * :py:class:`MySQLDatabase`
  * :py:class:`PooledMySQLDatabase`
* Postgres
  * :py:class:`PostgresqlDatabase`
  * :py:class:`PostgresqlExtDatabase` - supports additional Postgresql-specific
    functionality, such as: JSON(B), HStore, arrays, full-text search, etc.
  * :py:class:`PooledPostgresqlDatabase`
  * :py:class:`PooledPostgresqlExtDatabase`

If you're not sure which database class to use, select the first one listed.

Database instances are initialized with the name of the database followed by
any arbitrary keyword arguments that should be passed to the DB-API 2.0 driver.

Sqlite examples
^^^^^^^^^^^^^^^

.. code-block:: python

    # SQLite in-memory database, great for prototyping or testing.
    db = SqliteDatabase(':memory:')

    # SQLite database declaration I use on my blog. The "cached_statements"
    # parameter is supported by the pysqlite driver and determines the size of
    # the internal sqlite3_stmt cache. The "pragmas" parameter is a special
    # feature of the SqliteDatabase class, and allows the specification of
    # SQLite configuration settings to be run on every connection.
    from playhouse.sqlite_ext import SqliteExtDatabase

    db = SqliteExtDatabase('app.db', cached_statements=200, pragmas=(
        ('cache_size', -48 * 1000),  # SQLite shall use 48MB for caching pages.
        ('foreign_keys', 'on'),  # Enforce foreign key constraints.
        ('ignore_check_constraints', 'off'),  # Enforce CHECK constraints.
        ('journal_mode', 'wal'),  # Use WAL-mode **you probably want this**.
        ('synchronous', 0)))  # Rely on Linux to handle the filesystem.

MySQL example
^^^^^^^^^^^^^

.. code-block:: python

    # MySQL database running locally as specific user. Note that MySQL uses
    # "passwd" instead of "password".
    db = MySQLDatabase('my_application', user='mysql', passwd='secret')

Postgresql examples
^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    # Postgresql database running on a dedicated server.
    db = PostgresqlDatabase(
        'production_db',
        user='postgres',
        password=os.environ['PGPASSWORD'],  # Get password from environment.
        host=os.environ['PGHOST'])  # Get host from environment.

    # Postgresql with a connection pool and support for postgres-specific
    # extensions.
    from playhouse.pool import PooledPostgresqlExtDatabase

    db = PooledPostgresqlExtDatabase(
        'production_db',
        user='postgres',
        register_hstore=True,  # Enable support for Postgresql HStore.
        max_connections=64,  # Maximum number of connections supported by pool.
        stale_timeout=300)  # Prevent connections from getting stale when idle.

Executing SQL queries directly
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The :py:meth:`Database.execute_sql` method can be used to directly execute a
SQL query. The method accepts the following parameters:

* SQL query.
* Query parameter ``tuple`` (optional)
* Boolean value indicating whether to COMMIT immediately afterwards.

The :py:meth:`~Database.execute_sql` method returns a DB-API 2.0 ``Cursor``
object, which supports methods like ``fetchone()`` and ``fetchall()``. See the
:ref:`Python DB-API 2.0 documentation
<https://www.python.org/dev/peps/pep-0249/>`_ for details.

Example:

.. code-block:: python

    db = SqliteDatabase(':memory:')
    db.execute_sql('CREATE TABLE "test" ("data" TEXT);')
    db.execute_sql('INSERT INTO "test" ("data") VALUES (?), (?), (?)',
                   ('foo', 'bar', 'baz'))
    cursor = db.execute_sql('SELECT "data" FROM "test" ORDER BY "data"')
    for data, in cursor.fetchall():
        print data

Transactions
^^^^^^^^^^^^

Transactions are managed using the :py:meth:`Database.atomic` method, which
acts as either a context-manager or decorator. Calls to
:py:meth:`~Database.atomic` can be nested.

At the beginning of the wrapped block, either a transaction or a savepoint will
be opened (which one depends on the level of nesting). If the wrapped code
exits normally, then any changes are persisted. If an exception occurs, then
the changes are rolled back.

Example:

.. code-block:: python

    with db.atomic() as txn:
        # Make some changes to the database.
        db.execute_sql('UPDATE "accounts" SET "is_active" = %s '
                       'WHERE "last_login" < %s ', (False, date(2017, 1, 1)))

Transactions are covered in more detail in the :ref:`transactions` section.

Thread-safety
^^^^^^^^^^^^^

Database instances can be used across multiple threads so long as your
application is calling :py:meth:`~Database.connect` and
:py:meth:`~Database.close` from within each thread. For example, a web
application that uses threads to handle requests would need to connect to the
database when processing the request and then close the database when sending
the response.

Working with Tables
-------------------

Peewee provides both high- and low-level APIs for working with tables and
tabular data. This section will cover the high-level :py:class:`Model` and
:py:class:`Field` APIs.

.. note::
    For information on the low-level APIs see the :py:class:`Table`
    documentation.

The high-level APIs have the following correspondence with relational database
structures:

* :py:class:`Model` class : database table
* :py:class:`Field` instance : column on a table
* :py:class:`Model` instance : row in database table

Example model declaration:

.. code-block:: python

    app_db = SqliteDatabase('app.db')

    class Account(Model):
        # List of columns on the account table.
        first_name = TextField()
        last_name = TextField()
        email = CharField(unique=True)
        is_active = BooleanField(default=True)
        is_admin = BooleanField(default=False)
        created = DateTimeField(default=datetime.now)

        # Table-specific configuration is defined in an inner class named Meta.
        class Meta:
            database = app_db  # Specify which database to use.
            indexes = (
                # Create a non-unique index on last_name and first_name.
                (('last_name', 'first_name'), False),
            )


In the above example, take note of the following:

* We did not declare a primary key in the above example. By default, Peewee
  will automatically create an auto-incrementing integer primary key named
  "id" for models that do not explicitly declare a primary key.
* The ``email`` field is instantiated with ``unique=True``. When creating the
  ``Account`` table, peewee will also create a unique index on the ``email``
  column.
* The ``created`` field has a default of ``datetime.now``. Note that the
  default is a callable (as opposed to a function invocation). When saving a
  new ``Account``, if no value was provided for the ``created`` field, then
  Peewee will call ``datetime.now()`` and assign the return value to the field.
* The ``Account`` model is linked to the application database in an inner class
  named ``Meta``. The ``Meta`` inner class is used for table configuration and
  supports a number of additional attributes.
* Multi-column indexes are specified using ``Meta.indexes``, and take the form
  of: zero or more 2-tuples consisting of a tuple of field names and a boolean
  indicating whether the index is unique.

Helpful references:

* :ref:`Field types <field_types>`
* :ref:`Model meta options <meta_options>`

Using a base model class
^^^^^^^^^^^^^^^^^^^^^^^^

Quite often, an application will use more than one table. In this case, we can
make our code more readable and less repetitive by placing common configuration
in a base model class, and then using inheritance to declare our application
models.

.. code-block:: python

    app_db = SqliteDatabase('my_app.db')

    class BaseModel(Model):
        class Meta:
            database = app_db

    class Account(BaseModel):
        first_name = TextField()
        last_name = TextField()
        email = CharField(unique=True)
        is_active = BooleanField(default=True)
        is_admin = BooleanField(default=False)
        created = DateTimeField(default=datetime.now)

        class Meta:
            indexes = (
                (('last_name', 'first_name'), False),
            )

    class Note(BaseModel):
        account = ForeignKeyField(Account, backref='notes')
        content = TextField()
        created = DateTimeField(default=datetime.now, index=True)

Creating the schema
^^^^^^^^^^^^^^^^^^^

If you are starting a new project, Peewee can automatically create the schema
defined by your model classes.

To create the table and indexes for a single model class, use
:py:meth:`Model.create_table`.

.. code-block:: python

    with app_db:
        Account.create_table()
        Note.create_table()

.. note::

    We used the database instance as a context manager to wrap the calls to
    :py:meth:`~Model.create_table`. This wraps the operations in a transaction
    and ensures that the database connection used to create the tables is
    properly closed afterwards.

Peewee has a nice feature which will create the tables and indexes for a list
of models, automatically resolving foreign key dependencies to ensure the
tables are created in the correct order. See :py:meth:`Database.create_tables`.

.. code-block:: python

    with app_db:
        # Resolves dependencies and creates tables in correct order.
        app_db.create_tables([Account, Note])

.. note::

    If you are working with an existing database, you can use the :ref:`pwiz`
    script to auto-generate model definitions from your existing schema.

    If you wish to modify an existing database schema, you can use the
    :ref:`migrations` extension library to code the schema changes in Python.

Storing data
^^^^^^^^^^^^

Model classes operate in two ways:

* As a class, which represents the table.
* As an instance, which represents a row in the table.

The simplest way to store data in the database is to use the
:py:meth:`~Model.create` classmethod:

.. code-block:: python

    huey = Account.create(first_name='huey', last_name='cat', email='meow@cats.com')
    print(huey.first_name, huey.last_name)
    print('Huey\'s primary key is:', huey.id)

:py:meth:`~Model.create` inserts a new row in the database and returns a model
instance with the specified values. If the model class has an auto-incrementing
primary key, then the primary key will be populated as well.

You can also create new rows piecemeal by instantiating a model, assigning
values to the attributes, and calling the :py:meth:`~Model.save` method:

.. code-block:: python

    mickey = Account(first_name='mickey', last_name='dog')
    mickey.email = 'woof@dogs.com'
    mickey.save()
    print(mickey.first_name, 'has a primary key value of', mickey.id)

You can make modifications to the model instance and call
:py:meth:`~Model.save` afterwards to update a row. For example:

.. code-block:: python

    # Change mickey's email address.
    mickey.email = 'woof1@dogs.com'
    mickey.save()

Instead of creating a new row, this will update the existing row.

See also:

* :py:meth:`Model.insert`, :py:meth:`Model.insert_many`,
  :py:meth:`Model.insert_from`
* :py:meth:`Model.update`

Retrieving data
^^^^^^^^^^^^^^^

Peewee supports several methods for retrieving data, and which one you use is
determined by whether you expect to get a single row of data back, or are
fetching multiple rows based on a particular query.

To retrieve a single row, we can use :py:meth:`Model.get`, which returns the
first matching row or raises a :py:class:`DoesNotExist` exception if no rows
matched:

.. code-block:: python

    mickey = Account.get(
        (Account.first_name == 'mickey') &
        (Account.last_name == 'dog'))
    print('Mickey\'s email is:', mickey.email)

.. note::
    If you prefer a return value of ``None`` if no rows were matched, use
    :py:meth:`Model.get_or_none`.

To retrieve zero or more rows, as well as to have greater control over which
columns are selected, we can use :py:meth:`Model.select`.

.. code-block:: python

    catdotcom_users = Account.select().where(Account.email.endswith('@cat.com'))
    for account in catdotcom_users:
        print(account.email, '->', account.first_name, account.last_name)

The filters applied in the :py:meth:`~Select.where` method will be described in
the next chapter on :ref:`sql_expressions`.

Deleting data
^^^^^^^^^^^^^

To delete a single row of data, you can use the
:py:meth:`~Model.delete_instance` method:

.. code-block:: python

    mickey.delete_instance()

By default, this will only delete the given row. If there are other rows that
are dependent on a particular model instance (for example, any notes that may
have been associated with an account), you can specify that
:py:meth:`~Model.delete_instance` recursively delete dependencies:

.. code-block:: python

    # Retrieve an account from the database by doing an exact lookup
    # on the email column.
    huey = Account.get(Account.email == 'meow@cats.com')

    # Create two notes associated with the account via foreign key.
    Note.create(account=huey, content='meow')
    Note.create(account=huey, content='purr')

    # Delete the account recursively, which also deletes the 2 notes.
    huey.delete_instance(recursive=True)

To perform a delete on an arbitrary number of rows, use the
:py:meth:`~Model.delete` classmethod:

.. code-block:: python

    # Delete inactive accounts.
    n_removed = (Account
                 .delete()
                 .where(Account.is_active == False)
                 .execute())

The number of rows removed will be returned.

.. note::

    To execute a ``DELETE`` query (or ``INSERT`` or ``UPDATE``), don't forget
    to call the query's ``execute()`` method.

.. _sql_expressions:

SQL Expressions
---------------

Peewee provides a flexible and expressive SQL engine. Individual SQL components
can be combined in predictable, reusable ways using simple Python APIs.

Query operator table
^^^^^^^^^^^^^^^^^^^^

The following table lists the comparison operations supported by Peewee:

================ =======================================
Comparison       Meaning
================ =======================================
``==``           x equals y
``<``            x is less than y
``<=``           x is less than or equal to y
``>``            x is greater than y
``>=``           x is greater than or equal to y
``!=``           x is not equal to y
``<<``           x IN y, where y is a list or query
``%``            x LIKE y where y may contain wildcards
``**``           x ILIKE y where y may contain wildcards
``~``            Negation
================ =======================================

Because I ran out of operators to override, there are some additional query
operations available as methods:

======================= ===============================================
Method                  Meaning
======================= ===============================================
``.in_(value)``         IN lookup (identical to ``<<``).
``.not_in(value)``      NOT IN lookup.
``.is_null(is_null)``   IS NULL or IS NOT NULL. Accepts boolean param.
``.contains(substr)``   Wild-card search for substring.
``.startswith(prefix)`` Search for values beginning with ``prefix``.
``.endswith(suffix)``   Search for values ending with ``suffix``.
``.between(low, high)`` Search for values between ``low`` and ``high``.
``.regexp(exp)``        Regular expression match.
``.bin_and(value)``     Binary AND.
``.bin_or(value)``      Binary OR.
``.concat(other)``      Concatenate two strings using ``||``.
======================= ===============================================

To combine clauses using logical operators, use:

================ ==================== =================================================================
Operator         Meaning              Example
================ ==================== =================================================================
``&``            AND                  ``(Account.first_name == 'huey') & (Account.last_name == 'cat')``
``|`` (pipe)     OR                   ``(Account.is_active) | (Account.is_admin)``
``~``            NOT (unary negation) ``~Account.is_active``
================ ==================== =================================================================

Here is how you might use some of these query operators:

.. code-block:: python

    # Find accounts for people named "huey".
    Account.select().where(Account.first_name == 'huey')

    # Find the users whose username is in [huey, mickey, zaizee]
    (Account
     .select()
     .where(Account.first_name.in_(['huey', 'mickey', 'zaizee'])))

    # Find employees who are making between 50K and 60K.
    Employee.select().where(Employee.salary.between(50000, 60000))

    Employee.select().where(Employee.name.startswith('C'))

    Note.select().where(Note.content.contains(search_string))

Here is how you might combine expressions. Comparisons can be arbitrarily
complex.

.. note::
    Note that the actual comparisons are wrapped in parentheses. Python's
    operator precedence necessitates that comparisons be wrapped in
    parentheses.

.. code-block:: python

    # Find any accounts who are active administrations.
    Account.select().where(
      (Account.is_active == True) &
      (Account.is_admin == True))

    # Find any accounts where the email ends with "cats.com" or "dogs.com".
    Account.select().where(
      Account.email.endswith('@cats.com') |
      Account.email.endswith('@dogs.com'))

    # Find any Note objects associated with Accounts that are not active.
    inactive = Account.select(Account.id).where(~Account.is_active)
    inactive_notes = Note.select().where(Note.account.in_(inactive))

.. warning::
    Although you may be tempted to use python's ``in``, ``and``, ``or`` and
    ``not`` operators in your query expressions, these **will not work.** The
    return value of an ``in`` expression is always coerced to a boolean value.
    Similarly, ``and``, ``or`` and ``not`` all treat their arguments as boolean
    values and cannot be overloaded.

    So just remember:

    * Use ``in_()`` instead of ``in``
    * Use ``&`` instead of ``and``
    * Use ``|`` instead of ``or``
    * Use ``~`` instead of ``not``
    * Don't forget to **wrap your comparisons in parentheses** when using
      logical operators.

Three valued logic
^^^^^^^^^^^^^^^^^^

Because of the way SQL handles ``NULL``, there are some special operations
available for expressing:

* ``IS NULL``
* ``IS NOT NULL``
* ``IN``
* ``NOT IN``

While it would be possible to use the ``is_null()`` and ``in_()`` methods with
the negation operator (``~``), sometimes to get the correct semantics you will
need to explicitly use ``IS NOT NULL`` and ``NOT IN``.

Here are examples using ``IS NULL`` and ``IN``:

.. code-block:: python

    # Get all Employees whose start date is NULL.
    Employee.select().where(Employee.start_date.is_null())

    # Get accounts for people with the given first names.
    names = ['huey', 'mickey', 'zaizee']
    Account.select().where(Account.first_name.in_(usernames))

To negate the above queries with the correct semantics you need to use the
special ``IS NOT NULL`` and ``NOT IN`` operators:

.. code-block:: python

    # Get all Employees whose start date is *NOT* NULL.
    Employee.select().where(Employee.start_date.is_null(False))

    # Get accounts for people whose first name is *NOT* included in the list.
    names = ['huey', 'mickey', 'zaizee']
    Account.select().where(Account.first_name.not_in(usernames))

Query Evaluation
----------------
