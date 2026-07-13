"""Create the jobs table (database queue driver)."""

from arvel.database import Migration


class CreateJobsTable(Migration):
    def up(self, schema):
        def define(t):
            t.id()
            t.string("queue").index()
            t.text("payload")
            t.integer("attempts")
            t.integer("reserved_at").nullable()
            t.integer("available_at")
            t.integer("created_at")

        schema.create("jobs", define)

    def down(self, schema):
        schema.drop("jobs")
