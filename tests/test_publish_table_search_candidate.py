"""Publication guards and exact verification use fake providers and stores."""
import copy
import json
from types import SimpleNamespace as NS
from unittest.mock import Mock

import numpy as np
import pytest
import yaml
from qdrant_client.models import Distance

from scripts.build_table_search_candidate import ROOT, build_candidate
from scripts.publish_table_search_candidate import prepare_candidate, publish_candidate, validate_vectors, verify_stores


class FakeCollection:
    def __init__(self, docs=()):
        self.docs = {d["_id"]: copy.deepcopy(d) for d in docs}

    def count_documents(self, query):
        return len(self.docs)

    def insert_many(self, docs, ordered):
        assert ordered
        for d in docs:
            assert d["_id"] not in self.docs
            self.docs[d["_id"]] = copy.deepcopy(d)

    def find(self, query):
        return list(self.docs.values())


class FakeDatabase:
    def __init__(self):
        self.collections = {"baseline_mongo": FakeCollection([{"_id": "original"}])}

    def __getitem__(self, name):
        return self.collections[name]

    def list_collection_names(self):
        return list(self.collections)

    def create_collection(self, name):
        assert name not in self.collections and name == "candidate_mongo"
        self.collections[name] = FakeCollection()
        return self.collections[name]


class FakeQdrant:
    def __init__(self):
        self.points = {}
        self.created = False

    def collection_exists(self, name):
        assert name == "candidate_qdrant"
        return self.created

    def count(self, name, exact):
        assert name == "baseline_qdrant" and exact
        return NS(count=1)

    def create_collection(self, name, vectors_config):
        assert name == "candidate_qdrant" and not self.created
        self.created, self.config = True, vectors_config

    def create_payload_index(self, **kwargs):
        assert kwargs["collection_name"] == "candidate_qdrant"

    def upsert(self, name, points, wait):
        assert name == "candidate_qdrant" and wait
        self.points.update({str(p.id): p for p in points})

    def scroll(self, name, **kwargs):
        assert name == "candidate_qdrant" and kwargs["with_vectors"]
        return list(self.points.values()), None

    def get_collection(self, name):
        assert name == "candidate_qdrant"
        return NS(config=NS(params=NS(vectors=self.config)))


def tiny_candidate(tmp_path):
    return {"directory": tmp_path,
            "manifest": {"storage_targets": {"qdrant_collection": "candidate_qdrant", "mongo_parent_collection": "candidate_mongo"},
                         "embedding": {"dimension": 2}},
            "source": {"storage_targets": {"qdrant_collection": "baseline_qdrant", "mongo_parent_collection": "baseline_mongo"}},
            "chunks": [{"_id": "c1", "content": "text", "metadata": {"cohort": "K51", "parent_section_id": "p1"}}],
            "parents": [{"_id": "p1", "cohort": "K51", "content": "Full source"}]}


def test_real_candidate_is_verified_locally_before_model_calls(tmp_path):
    build_candidate(ROOT, tmp_path, ROOT / "configs/table_search_descriptions.yaml")
    prepared = prepare_candidate(ROOT, tmp_path)
    assert len(prepared["chunks"]) == 3835 and len(prepared["parents"]) == 541
    path = tmp_path / "candidate_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["storage_targets"]["qdrant_collection"] = "student_handbook_semantic_v35"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="storage targets"):
        prepare_candidate(ROOT, tmp_path)


@pytest.mark.parametrize("field,value", [("api_url", "https://not-authorized.example/embeddings"),
                                        ("api_key_env_var", "OTHER_SECRET")])
def test_candidate_cannot_redirect_corpus_or_embedding_key(tmp_path, field, value):
    build_candidate(ROOT, tmp_path, ROOT / "configs/table_search_descriptions.yaml")
    path = tmp_path / "retrieval.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["embedding"][field] = value
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    with pytest.raises(ValueError, match="provider/runtime"):
        prepare_candidate(ROOT, tmp_path)


@pytest.mark.parametrize("registry,accepted", [
    # Built in another checkout of the repository: same file, same hash.
    ("C:/other/checkout/data/processed/tables/structured_tables_registry.json", True),
    ("C:/other/checkout/data/processed/tables/other_registry.json", False),
])
def test_candidate_from_another_checkout_must_name_the_same_registry(tmp_path, registry, accepted):
    build_candidate(ROOT, tmp_path, ROOT / "configs/table_search_descriptions.yaml")
    path = tmp_path / "retrieval.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    config["retrieval"]["table_search"]["registry_path"] = registry
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    if accepted:
        assert len(prepare_candidate(ROOT, tmp_path)["chunks"]) == 3835
    else:
        with pytest.raises(ValueError, match="retrieval contract"):
            prepare_candidate(ROOT, tmp_path)


@pytest.mark.parametrize("store", ["qdrant", "mongo", "local_vectors"])
def test_collision_refuses_embedding_and_preserves_baseline(tmp_path, store):
    prepared, qdrant, db = tiny_candidate(tmp_path), FakeQdrant(), FakeDatabase()
    if store == "qdrant":
        qdrant.created = True
    elif store == "mongo":
        db.collections["candidate_mongo"] = FakeCollection()
    else:
        (tmp_path / "embeddings_full.npy").write_bytes(b"preserve")
    embedder = Mock()
    with pytest.raises(FileExistsError):
        publish_candidate(prepared, qdrant, db, embedder, {})
    embedder.embed_documents.assert_not_called()
    assert db["baseline_mongo"].docs == {"original": {"_id": "original"}}


@pytest.mark.parametrize("vectors", [[[0.0, 0.0]], [[float("nan"), 0.8]], [[0.6, 0.8, 0.1]], []])
def test_invalid_vectors_rejected(vectors):
    with pytest.raises(ValueError):
        validate_vectors(vectors, 1, 2)


def test_publish_saves_vectors_before_writes_and_verifies_every_payload(tmp_path):
    prepared, qdrant, db = tiny_candidate(tmp_path), FakeQdrant(), FakeDatabase()
    embedder = NS(embed_documents=lambda texts: [[0.6, 0.8]])
    original_create = qdrant.create_collection
    def create(name, vectors_config):
        assert (tmp_path / "embeddings_full.npy").is_file()
        original_create(name, vectors_config)
    qdrant.create_collection = create
    report = publish_candidate(prepared, qdrant, db, embedder, {})
    assert report["completed"] and not report["production_activated"]
    assert report["verification"]["verified_vectors"] == 1
    assert report["verification"]["verified_parents"] == 1
    assert report["baseline_before"] == report["baseline_after"]
    assert qdrant.config.distance == Distance.COSINE
    vectors = np.load(tmp_path / "embeddings_full.npy", allow_pickle=False)
    point = next(iter(qdrant.points.values()))
    point.payload["cohort"] = "K50"
    with pytest.raises(ValueError, match="payload"):
        verify_stores(prepared, qdrant, db, vectors)


def test_target_race_after_embeddings_never_overwrites_collection(tmp_path):
    prepared, qdrant, db = tiny_candidate(tmp_path), FakeQdrant(), FakeDatabase()
    def embed(texts):
        qdrant.created = True
        return [[0.6, 0.8]]
    with pytest.raises(FileExistsError):
        publish_candidate(prepared, qdrant, db, NS(embed_documents=embed), {})
    assert (tmp_path / "embeddings_full.npy").is_file()
    assert not qdrant.points and list(db.collections) == ["baseline_mongo"]
