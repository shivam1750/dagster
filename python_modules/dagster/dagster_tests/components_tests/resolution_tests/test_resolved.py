from dataclasses import dataclass, field
from typing import Annotated, Literal, Optional, Union

import pytest
from dagster._core.definitions.asset_key import AssetKey
from dagster._core.definitions.definitions_class import Definitions
from dagster.components import Component, Model, Resolvable, ResolvedAssetSpec
from dagster.components.resolved.errors import ResolutionException
from dagster.components.resolved.model import Resolver
from pydantic import BaseModel, ConfigDict, Field


def test_basic():
    @dataclass
    class MyThing(Resolvable):
        name: str

    MyThing.resolve_from_yaml(
        """
name: hello
        """
    )


def test_error():
    class Foo: ...

    @dataclass
    class MyNewThing(Resolvable):
        name: str
        foo: Foo

    with pytest.raises(ResolutionException, match="Could not derive resolver for annotation foo:"):
        MyNewThing.resolve_from_yaml("")


def test_nested():
    @dataclass
    class OtherThing(Resolvable):
        num: int

    @dataclass
    class MyThing(Resolvable):
        name: str
        other_thing: OtherThing
        other_things: Optional[list[OtherThing]]

    MyThing.resolve_from_yaml(
        """
name: hi
other_thing:
    num: 4
other_things:
    - num: 4
""",
    )


def test_custom_resolution():
    class Foo:
        def __init__(self, name):
            self.name = name

    def _resolve_foo(context, name: str):
        return Foo(name)

    @dataclass
    class MyThing(Resolvable):
        name: str
        foo: Annotated[
            Foo,
            Resolver(
                _resolve_foo,
                model_field_type=str,
                model_field_name="foo_name",
            ),
        ]
        stuff: list[str] = field(default_factory=list)

    thing = MyThing.resolve_from_yaml(
        """
name: hello
foo_name: steve
"""
    )
    assert thing.foo.name == "steve"


def test_py_model():
    class Foo:
        def __init__(self, name):
            self.name = name

    def _resolve_foo(context, name: str):
        return Foo(name)

    class MyThing(Resolvable, BaseModel):
        model_config = ConfigDict(arbitrary_types_allowed=True)  # to allow Foo

        name: str = "bad"
        foo: Annotated[
            Foo,
            Resolver(
                _resolve_foo,
                model_field_type=str,
                model_field_name="foo_name",
            ),
        ]

    thing = MyThing.resolve_from_yaml(
        """
foo_name: steve
"""
    )
    assert thing.name == "bad"
    assert thing.foo.name == "steve"


def test_legacy_core_components_compat():
    @dataclass
    class Example(Resolvable):
        asset_specs: list[ResolvedAssetSpec]

    ex = Example.resolve_from_yaml("""
asset_specs:
    - key: foo
    - key: bar
""")

    assert ex.asset_specs[0].key == AssetKey("foo")


def test_class():
    class Person(Resolvable):
        random: str  # ensure random annotations ignored

        def __init__(
            self,
            name: str,
            age: int,
        ): ...

    Person.resolve_from_yaml(
        """
name: Rei
age: 7
""",
    )

    class Flexible(Resolvable):
        def __init__(
            self,
            *args,
            name: str,
            **kwargs,
        ): ...

    Flexible.resolve_from_yaml(
        """
name: flex
    """,
    )


def test_bad_class():
    class Empty(Resolvable): ...

    with pytest.raises(ResolutionException, match="class with __init__"):
        Empty.resolve_from_yaml("")

    class JustSelf(Resolvable):
        def __init__(
            self,
        ): ...

    JustSelf.resolve_from_yaml("")

    class PosOnly(Resolvable):
        def __init__(
            self,
            a: int,
            /,
            b: int,
        ): ...

    with pytest.raises(ResolutionException, match="positional only parameter"):
        PosOnly.resolve_from_yaml("")


def test_component_docs():
    class RangeTest(Model):
        type: Literal["range"] = Field(..., description="Must be 'range'.")
        name: str

    class SumTest(Model):
        type: Literal["sum"] = Field(..., description="Must be 'sum'")
        name: str

    class TestSuiteComponent(Component, Resolvable, Model):
        asset_key: str = Field(
            ..., description="The asset key to test. Slashes are parsed into key parts."
        )
        tests: list[Union[RangeTest, SumTest]]

        def build_defs(self, context):
            return Definitions()

    model_cls = TestSuiteComponent.get_model_cls()
    assert model_cls
    assert model_cls.model_fields["asset_key"].description
    json_schema = model_cls.model_json_schema()
    assert json_schema["$defs"]["RangeTest"]["properties"]["type"]["description"]
    assert json_schema["$defs"]["SumTest"]["properties"]["type"]["description"]
