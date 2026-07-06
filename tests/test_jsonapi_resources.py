"""JSON:API resource documents — type/id/attributes, loaded-relation linkage + include,
sparse fieldsets, paginator links/meta. Pure transform layer; the served media type and the
errors[] shape are pinned in the http tests."""

from __future__ import annotations

from typing import Any

from arvel.database.resources import JsonApiResource

# --- stand-ins: the resource layer only relies on to_dict()/_relations/pk ----------


class FakeModel:
    __primary_key__ = "id"

    def __init__(self, data: dict[str, Any], relations: dict[str, Any] | None = None) -> None:
        self._data = data
        self._relations = relations or {}

    def to_dict(self) -> dict[str, Any]:
        return dict(self._data)


class FakeRequest:
    def __init__(self, params: dict[str, str] | None = None) -> None:
        self._params = params or {}

    def query(self, key: str, default: Any = None) -> Any:
        return self._params.get(key, default)


class AuthorResource(JsonApiResource[FakeModel]):
    resource_type = "authors"


class PostResource(JsonApiResource[FakeModel]):
    resource_type = "posts"
    relationships = {"author": AuthorResource}


def _post(**relations: Any) -> FakeModel:
    return FakeModel({"id": 7, "title": "Hello", "body": "world"}, relations)


def test_single_document_shape() -> None:
    doc = PostResource(_post()).to_payload(FakeRequest())
    assert doc == {
        "data": {
            "type": "posts",
            "id": "7",
            "attributes": {"title": "Hello", "body": "world"},
        }
    }


def test_loaded_relationship_renders_linkage_and_include() -> None:
    author = FakeModel({"id": 3, "name": "Ada"})
    doc = PostResource(_post(author=author)).to_payload(FakeRequest({"include": "author"}))
    assert doc["data"]["relationships"] == {"author": {"data": {"type": "authors", "id": "3"}}}
    assert doc["included"] == [{"type": "authors", "id": "3", "attributes": {"name": "Ada"}}]


def test_unloaded_relationship_is_omitted() -> None:
    doc = PostResource(_post()).to_payload(FakeRequest({"include": "author"}))
    assert "relationships" not in doc["data"]
    assert "included" not in doc


def test_include_not_requested_keeps_linkage_but_no_included() -> None:
    author = FakeModel({"id": 3, "name": "Ada"})
    doc = PostResource(_post(author=author)).to_payload(FakeRequest())
    assert doc["data"]["relationships"]["author"]["data"] == {"type": "authors", "id": "3"}
    assert "included" not in doc


def test_unknown_include_name_is_ignored() -> None:
    doc = PostResource(_post()).to_payload(FakeRequest({"include": "nope"}))
    assert "included" not in doc


def test_sparse_fieldsets_filter_attributes_and_ignore_unknown_names() -> None:
    author = FakeModel({"id": 3, "name": "Ada", "bio": "…"})
    doc = PostResource(_post(author=author)).to_payload(
        FakeRequest({"include": "author", "fields[posts]": "title,ghost", "fields[authors]": "bio"})
    )
    assert doc["data"]["attributes"] == {"title": "Hello"}  # ghost silently dropped
    assert doc["included"][0]["attributes"] == {"bio": "…"}


def test_to_many_relationship_linkage() -> None:
    posts = [FakeModel({"id": 1, "title": "a"}), FakeModel({"id": 2, "title": "b"})]

    class AuthorWithPosts(JsonApiResource[FakeModel]):
        resource_type = "authors"
        relationships = {"posts": PostResource}

    author = FakeModel({"id": 3, "name": "Ada"}, {"posts": posts})
    doc = AuthorWithPosts(author).to_payload(FakeRequest({"include": "posts"}))
    assert doc["data"]["relationships"]["posts"]["data"] == [
        {"type": "posts", "id": "1"},
        {"type": "posts", "id": "2"},
    ]
    assert [item["id"] for item in doc["included"]] == ["1", "2"]


def test_included_deduplicates_by_type_and_id() -> None:
    author = FakeModel({"id": 3, "name": "Ada"})
    posts = [_post(author=author), _post(author=author)]
    doc = PostResource.collection(posts).to_payload(FakeRequest({"include": "author"}))
    assert len(doc["included"]) == 1


def test_collection_over_list() -> None:
    doc = PostResource.collection([_post()]).to_payload(FakeRequest())
    assert doc["data"][0]["type"] == "posts"


def test_collection_over_paginator_links_and_meta() -> None:
    from arvel.pagination import LengthAwarePaginator

    paginator = LengthAwarePaginator(
        items=[_post()], total=7, per_page=1, current_page=2, path="/posts"
    )
    doc = PostResource.collection(paginator).to_payload(FakeRequest())
    assert [item["type"] for item in doc["data"]] == ["posts"]
    links = doc["links"]
    assert links["first"] and links["last"] and links["prev"] and links["next"]
    assert doc["meta"]["total"] == 7


def test_collection_over_empty_paginator() -> None:
    from arvel.pagination import LengthAwarePaginator

    paginator = LengthAwarePaginator(items=[], total=0, per_page=10, current_page=1, path="/posts")
    doc = PostResource.collection(paginator).to_payload(FakeRequest())
    assert doc["data"] == []
    assert doc["links"]["next"] is None


def test_to_array_falls_back_to_mapping_for_plain_dicts() -> None:
    doc = PostResource({"id": 5, "title": "raw"}).to_payload(FakeRequest())  # type: ignore[arg-type]
    assert doc["data"] == {"type": "posts", "id": "5", "attributes": {"title": "raw"}}


def test_when_loaded_callback_and_non_dict_relations() -> None:
    from arvel.database.resources import MISSING

    author = FakeModel({"id": 3, "name": "Ada"})
    post = _post(author=author)
    resource = PostResource(post)
    assert resource.when_loaded("author", lambda a: a.to_dict()["name"]) == "Ada"

    class Bare:  # no _relations mapping at all
        def to_dict(self) -> dict[str, Any]:
            return {"id": 9}

    assert PostResource(Bare()).when_loaded("author") is MISSING  # type: ignore[arg-type]


def test_document_renders_without_a_request() -> None:
    # queued serialization / CLI contexts pass no request: params simply read as absent
    doc = PostResource(_post()).to_payload(None)
    assert doc["data"]["attributes"] == {"title": "Hello", "body": "world"}


def test_null_to_one_relation_renders_null_linkage() -> None:
    doc = PostResource(_post(author=None)).to_payload(FakeRequest())
    assert doc["data"]["relationships"]["author"] == {"data": None}


def test_additional_meta_on_resource_and_collection() -> None:
    doc = PostResource(_post()).additional({"meta": {"trace": "t1"}}).to_payload(FakeRequest())
    assert doc["meta"] == {"trace": "t1"}
    coll = PostResource.collection([_post()]).additional({"meta": {"page": 1}})
    assert coll.to_payload(FakeRequest())["meta"] == {"page": 1}
