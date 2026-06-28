"""Create the notifications table (database notification channel)."""

from arvel.database import Migration


class CreateNotificationsTable(Migration):
    def up(self, schema):
        def define(t):
            t.uuid("id").primary()
            t.string("type")
            t.string("notifiable_type")
            t.string("notifiable_id").index()
            t.text("data")
            t.timestamp("read_at").nullable()
            t.timestamps()

        schema.create("notifications", define)

    def down(self, schema):
        schema.drop("notifications")
