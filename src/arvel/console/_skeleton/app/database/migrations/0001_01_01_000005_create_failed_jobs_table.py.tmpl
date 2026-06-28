"""Create the failed_jobs table (records jobs that exhausted their retries)."""

from arvel.database import Migration


class CreateFailedJobsTable(Migration):
    def up(self, schema):
        def define(t):
            t.uuid("id").primary()
            t.string("queue").index()
            t.text("payload")
            t.text("exception")
            t.timestamp("failed_at")

        schema.create("failed_jobs", define)

    def down(self, schema):
        schema.drop("failed_jobs")
