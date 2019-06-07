""" This module contains the error-related constants and classes. """
from abc import ABC, abstractmethod
from collections import defaultdict
from copy import copy, deepcopy
from pprint import pformat
from typing import (
    TYPE_CHECKING,
    cast,
    Any,
    MutableMapping,
    Optional,
    Dict,
    Union,
    Iterator,
    Iterable,
)

from typing import DefaultDict

from cerberus.typing import DocumentPath, FieldName
from cerberus.utils import compare_paths_lt, quote_string

if TYPE_CHECKING:
    from cerberus.base import UnconcernedValidator  # noqa: F401


class ErrorDefinition:
    """
    This class is used to define possible errors. Each distinguishable error is
    defined by a *unique* error ``code`` as integer and the ``rule`` that can
    cause it as string.
    The instances' names do not contain a common prefix as they are supposed to be
    referenced within the module namespace, e.g. ``errors.CUSTOM``.
    """

    __slots__ = ('code', 'rule')

    def __init__(self, code: int, rule: Optional[str]) -> None:
        self.code = code
        self.rule = rule


# custom
CUSTOM = ErrorDefinition(0x00, None)

# existence
DOCUMENT_MISSING = ErrorDefinition(0x01, None)  # issues/141
DOCUMENT_MISSING = "document is missing"  # type: ignore
REQUIRED_FIELD = ErrorDefinition(0x02, 'required')
UNKNOWN_FIELD = ErrorDefinition(0x03, None)
DEPENDENCIES_FIELD = ErrorDefinition(0x04, 'dependencies')
DEPENDENCIES_FIELD_VALUE = ErrorDefinition(0x05, 'dependencies')
EXCLUDES_FIELD = ErrorDefinition(0x06, 'excludes')

# shape
DOCUMENT_FORMAT = ErrorDefinition(0x21, None)  # issues/141
DOCUMENT_FORMAT = "'{0}' is not a document, must be a dict"  # type: ignore
EMPTY = ErrorDefinition(0x22, 'empty')
NULLABLE = ErrorDefinition(0x23, 'nullable')
TYPE = ErrorDefinition(0x24, 'type')
ITEMS_LENGTH = ErrorDefinition(0x26, 'items')
MIN_LENGTH = ErrorDefinition(0x27, 'minlength')
MAX_LENGTH = ErrorDefinition(0x28, 'maxlength')

# color
REGEX_MISMATCH = ErrorDefinition(0x41, 'regex')
MIN_VALUE = ErrorDefinition(0x42, 'min')
MAX_VALUE = ErrorDefinition(0x43, 'max')
UNALLOWED_VALUE = ErrorDefinition(0x44, 'allowed')
UNALLOWED_VALUES = ErrorDefinition(0x45, 'allowed')
FORBIDDEN_VALUE = ErrorDefinition(0x46, 'forbidden')
FORBIDDEN_VALUES = ErrorDefinition(0x47, 'forbidden')
MISSING_MEMBERS = ErrorDefinition(0x48, 'contains')

# other
NORMALIZATION = ErrorDefinition(0x60, None)
COERCION_FAILED = ErrorDefinition(0x61, 'coerce')
RENAMING_FAILED = ErrorDefinition(0x62, 'rename_handler')
READONLY_FIELD = ErrorDefinition(0x63, 'readonly')
SETTING_DEFAULT_FAILED = ErrorDefinition(0x64, 'default_setter')

# groups
ERROR_GROUP = ErrorDefinition(0x80, None)
SCHEMA = ErrorDefinition(0x81, 'schema')
ITEMSRULES = ErrorDefinition(0x82, 'itemsrules')
KEYSRULES = ErrorDefinition(0x83, 'keysrules')
VALUESRULES = ErrorDefinition(0x84, 'valuesrules')
ITEMS = ErrorDefinition(0x8F, 'items')

LOGICAL = ErrorDefinition(0x90, None)
NONEOF = ErrorDefinition(0x91, 'noneof')
ONEOF = ErrorDefinition(0x92, 'oneof')
ANYOF = ErrorDefinition(0x93, 'anyof')
ALLOF = ErrorDefinition(0x94, 'allof')


""" SchemaError messages """

MISSING_SCHEMA = "validation schema missing"
SCHEMA_TYPE = "schema definition for field '{0}' must be a dict"


""" Error representations """


class ValidationError:
    """ A simple class to store and query basic error information. """

    def __init__(
        self,
        document_path: DocumentPath,
        schema_path: DocumentPath,
        code: int,
        rule: str,
        constraint: Any,
        value: Any,
        info: Any,
    ) -> None:
        self.document_path = document_path
        """ The path to the field within the document that caused the error.
            Type: :class:`tuple` """
        self.schema_path = schema_path
        """ The path to the rule within the schema that caused the error.
            Type: :class:`tuple` """
        self.code = code
        """ The error's identifier code. Type: :class:`int` """
        self.rule = rule
        """ The rule that failed. Type: `string` """
        self.constraint = constraint
        """ The constraint that failed. """
        self.value = value
        """ The value that failed. """
        self.info = info
        """ May hold additional information about the error.
            Type: :class:`tuple` """

    def __eq__(self, other):
        """ Assumes the errors relate to the same document and schema. """
        return hash(self) == hash(other)

    def __hash__(self):
        """ Expects that all other properties are transitively determined. """
        return hash(self.document_path) ^ hash(self.schema_path) ^ hash(self.code)

    def __lt__(self, other):
        if self.document_path != other.document_path:
            return compare_paths_lt(self.document_path, other.document_path)
        else:
            return compare_paths_lt(self.schema_path, other.schema_path)

    def __repr__(self):
        return (
            "{class_name} @ {memptr} ( "
            "document_path={document_path},"
            "schema_path={schema_path},"
            "code={code},"
            "constraint={constraint},"
            "value={value},"
            "info={info} )".format(
                class_name=self.__class__.__name__,
                memptr=hex(id(self)),  # noqa: E501
                document_path=self.document_path,
                schema_path=self.schema_path,
                code=hex(self.code),
                constraint=quote_string(self.constraint),
                value=quote_string(self.value),
                info=self.info,
            )
        )

    @property
    def child_errors(self) -> Optional["ErrorList"]:
        """
        A list that contains the individual errors of a bulk validation error.
        """
        return self.info[0] if self.is_group_error else None

    @property
    def definitions_errors(self) -> Optional[DefaultDict[int, "ErrorList"]]:
        """
        Dictionary with errors of an *of-rule mapped to the index of the definition it
        occurred in. Returns :obj:`None` if not applicable.
        """
        if not self.is_logic_error:
            return None

        result = defaultdict(ErrorList)  # type: DefaultDict[int, ErrorList]
        for error in self.child_errors:  # type: ignore
            i = error.schema_path[len(self.schema_path)]
            result[i].append(error)
        return result

    @property
    def field(self) -> Optional[FieldName]:
        """ Field of the contextual mapping, possibly :obj:`None`. """
        if self.document_path:
            return self.document_path[-1]
        else:
            return None

    @property
    def is_group_error(self) -> bool:
        """ ``True`` for errors of bulk validations. """
        return bool(self.code & ERROR_GROUP.code)

    @property
    def is_logic_error(self) -> bool:
        """ ``True`` for validation errors against different schemas with
            *of-rules. """
        return bool(self.code & LOGICAL.code - ERROR_GROUP.code)

    @property
    def is_normalization_error(self) -> bool:
        """ ``True`` for normalization errors. """
        return bool(self.code & NORMALIZATION.code)


class ErrorList(list):
    """ A list for :class:`~cerberus.errors.ValidationError` instances that
        can be queried with the ``in`` keyword for a particular
        :class:`~cerberus.errors.ErrorDefinition`. """

    def __contains__(self, error_definition):
        if not isinstance(error_definition, ErrorDefinition):
            raise TypeError

        wanted_code = error_definition.code
        return any(x.code == wanted_code for x in self)


class ErrorTreeNode(MutableMapping):
    __slots__ = ('descendants', 'errors', 'parent_node', 'path', 'tree_root')

    def __init__(self, path: DocumentPath, parent_node: 'ErrorTreeNode') -> None:
        self.parent_node = parent_node  # type: Optional[ErrorTreeNode]
        self.tree_root = self.parent_node.tree_root  # type: ErrorTree
        self.path = path[: self.parent_node.depth + 1]
        self.errors = ErrorList()
        self.descendants = {}  # type: Dict[FieldName, ErrorTreeNode]

    def __contains__(self, item):
        if isinstance(item, ErrorDefinition):
            return item in self.errors
        else:
            return item in self.descendants

    def __delitem__(self, key):
        del self.descendants[key]

    def __iter__(self) -> Iterator[ValidationError]:
        return iter(self.errors)

    def __getitem__(
        self, item: Union[ErrorDefinition, FieldName]
    ) -> Union[Optional[ValidationError], Optional['ErrorTreeNode']]:
        if isinstance(item, ErrorDefinition):
            for error in self.errors:
                if item.code == error.code:
                    return error
            return None
        else:
            return self.descendants.get(item)

    def __len__(self):
        return len(self.errors)

    def __repr__(self):
        return self.__str__()

    def __setitem__(self, key: FieldName, value: "ErrorTreeNode") -> None:
        self.descendants[key] = value

    def __str__(self):
        return str(self.errors) + ',' + str(self.descendants)

    @property
    def depth(self) -> int:
        return len(self.path)

    @property
    def tree_type(self) -> str:
        return self.tree_root.tree_type

    def add(self, error: ValidationError) -> None:
        error_path = self._path_of_(error)

        key = error_path[self.depth]
        if key not in self.descendants:
            self[key] = ErrorTreeNode(error_path, self)

        node = cast(ErrorTreeNode, self[key])

        if len(error_path) == self.depth + 1:
            node.errors.append(error)
            node.errors.sort()
            if error.is_group_error:
                for child_error in error.child_errors:  # type: ignore
                    self.tree_root.add(child_error)
        else:
            node.add(error)

    def _path_of_(self, error):
        return getattr(error, self.tree_type + '_path')


class ErrorTree(ErrorTreeNode):
    """ Base class for :class:`~cerberus.errors.DocumentErrorTree` and
        :class:`~cerberus.errors.SchemaErrorTree`. """

    depth = 0
    parent = None
    path = ()

    def __init__(self, errors: Iterable[ValidationError] = ()) -> None:
        self.tree_root = self
        self.errors = ErrorList()
        self.descendants = {}
        for error in errors:
            self.add(error)

    def add(self, error: ValidationError) -> None:
        """ Add an error to the tree. """
        if not self._path_of_(error):
            self.errors.append(error)
            self.errors.sort()
        else:
            super().add(error)

    def fetch_errors_from(self, path: DocumentPath) -> ErrorList:
        """ Returns all errors for a particular path. """
        node = self.fetch_node_from(path)
        if node is None:
            return ErrorList()
        else:
            return node.errors

    def fetch_node_from(self, path: DocumentPath) -> ErrorTreeNode:
        """ Returns a node for a path. """
        context = self
        for key in path:
            context = context.get(key, None)
            if context is None:
                break
        return context


class DocumentErrorTree(ErrorTree):
    """ Implements a dict-like class to query errors by indexes following the
        structure of a validated document. """

    tree_type = 'document'


class SchemaErrorTree(ErrorTree):
    """ Implements a dict-like class to query errors by indexes following the
        structure of the used schema. """

    tree_type = 'schema'


class BaseErrorHandler(ABC):
    """ Base class for all error handlers. """

    def __init__(self, *args, **kwargs):
        """ Optionally initialize a new instance. """
        pass

    @abstractmethod
    def __call__(self, errors: Iterable[ValidationError]) -> Any:
        """ Returns errors in a handler-specific format. """
        raise NotImplementedError

    def __iter__(self) -> Iterator[Any]:
        """ Be a superhero and implement an iterator over errors. """
        raise NotImplementedError

    @abstractmethod
    def add(self, error: ValidationError) -> None:
        """ Add an error to the errors' container object of a handler.

        :param error: The error to add.
        """
        pass

    def emit(self, error: ValidationError) -> None:
        """ Optionally emits an error in the handler's format to a stream.
            Or light a LED, or even shut down a power plant.

        :param error: The error to emit.
        """
        pass

    def end(self, validator: "UnconcernedValidator") -> None:
        """ Gets called when a validation ends.

        :param validator: The calling validator.
        """
        pass

    def extend(self, errors: Iterable[ValidationError]) -> None:
        """ Adds all errors to the handler's container object. """
        for error in errors:
            self.add(error)

    def start(self, validator: "UnconcernedValidator") -> None:
        """ Gets called when a validation starts.

        :param validator: The calling validator.
        """
        pass


class ToyErrorHandler(BaseErrorHandler):
    def __call__(self, *args, **kwargs):
        raise RuntimeError('This is not supposed to happen.')

    add = __call__


class BasicErrorHandler(BaseErrorHandler):
    """ Models cerberus' legacy. Returns a :class:`dict`. When mangled
        through :class:`str` a pretty-formatted representation of that
        tree is returned.
    """

    messages = {
        0x00: "{0}",
        0x01: "document is missing",
        0x02: "required field",
        0x03: "unknown field",
        0x04: "field '{0}' is required",
        0x05: "depends on these values: {constraint}",
        0x06: "{0} must not be present with '{field}'",
        0x21: "'{0}' is not a document, must be a dict",
        0x22: "empty values not allowed",
        0x23: "null value not allowed",
        0x24: "must be of {constraint} type",
        0x26: "length of list should be {constraint}, it is {0}",
        0x27: "min length is {constraint}",
        0x28: "max length is {constraint}",
        0x41: "value does not match regex '{constraint}'",
        0x42: "min value is {constraint}",
        0x43: "max value is {constraint}",
        0x44: "unallowed value {value}",
        0x45: "unallowed values {0}",
        0x46: "unallowed value {value}",
        0x47: "unallowed values {0}",
        0x48: "missing members {0}",
        0x61: "field '{field}' cannot be coerced: {0}",
        0x62: "field '{field}' cannot be renamed: {0}",
        0x63: "field is read-only",
        0x64: "default value for '{field}' cannot be set: {0}",
        0x81: "mapping doesn't validate subschema: {0}",
        0x82: "one or more sequence-items don't validate: {0}",
        0x83: "one or more keys of a mapping  don't validate: {0}",
        0x84: "one or more values in a mapping don't validate: {0}",
        0x85: "one or more sequence-items don't validate: {0}",
        0x91: "one or more definitions validate",
        0x92: "none or more than one rule validate",
        0x93: "no definitions validate",
        0x94: "one or more definitions don't validate",
    }

    def __init__(self, tree: Dict = None) -> None:
        self.tree = {} if tree is None else tree

    def __call__(self, errors):
        self.clear()
        self.extend(errors)
        return self.pretty_tree

    def __str__(self):
        return pformat(self.pretty_tree)

    @property
    def pretty_tree(self) -> Dict:
        pretty = deepcopy(self.tree)
        for field in pretty:
            self._purge_empty_dicts(pretty[field])
        return pretty

    def add(self, error):
        # Make sure the original error is not altered with
        # error paths specific to the handler.
        error = deepcopy(error)

        self._rewrite_error_path(error)

        if error.is_logic_error:
            self._insert_logic_error(error)
        elif error.is_group_error:
            self._insert_group_error(error)
        elif error.code in self.messages:
            self._insert_error(
                error.document_path, self._format_message(error.field, error)
            )

    def clear(self):
        self.tree = {}

    def start(self, validator):
        self.clear()

    def _format_message(self, field, error):
        return self.messages[error.code].format(
            *error.info, constraint=error.constraint, field=field, value=error.value
        )

    def _insert_error(self, path, node):
        """ Adds an error or sub-tree to :attr:tree.

        :param path: Path to the error.
        :type path: Tuple of strings and integers.
        :param node: An error message or a sub-tree.
        :type node: String or dictionary.
        """
        field = path[0]
        if len(path) == 1:
            if field in self.tree:
                subtree = self.tree[field].pop()
                self.tree[field] += [node, subtree]
            else:
                self.tree[field] = [node, {}]
        elif len(path) >= 1:
            if field not in self.tree:
                self.tree[field] = [{}]
            subtree = self.tree[field][-1]

            if subtree:
                new = self.__class__(tree=copy(subtree))
            else:
                new = self.__class__()
            new._insert_error(path[1:], node)
            subtree.update(new.tree)

    def _insert_group_error(self, error):
        for child_error in error.child_errors:
            if child_error.is_logic_error:
                self._insert_logic_error(child_error)
            elif child_error.is_group_error:
                self._insert_group_error(child_error)
            else:
                self._insert_error(
                    child_error.document_path,
                    self._format_message(child_error.field, child_error),
                )

    def _insert_logic_error(self, error):
        field = error.field
        self._insert_error(error.document_path, self._format_message(field, error))

        for definition_errors in error.definitions_errors.values():
            for child_error in definition_errors:
                if child_error.is_logic_error:
                    self._insert_logic_error(child_error)
                elif child_error.is_group_error:
                    self._insert_group_error(child_error)
                else:
                    self._insert_error(
                        child_error.document_path,
                        self._format_message(field, child_error),
                    )

    def _purge_empty_dicts(self, error_list):
        subtree = error_list[-1]
        if not error_list[-1]:
            error_list.pop()
        else:
            for key in subtree:
                self._purge_empty_dicts(subtree[key])

    def _rewrite_error_path(self, error, offset=0):
        """
        Recursively rewrites the error path to correctly represent logic errors
        """
        if error.is_logic_error:
            self._rewrite_logic_error_path(error, offset)
        elif error.is_group_error:
            self._rewrite_group_error_path(error, offset)

    def _rewrite_group_error_path(self, error, offset=0):
        child_start = len(error.document_path) - offset

        for child_error in error.child_errors:
            relative_path = child_error.document_path[child_start:]
            child_error.document_path = error.document_path + relative_path

            self._rewrite_error_path(child_error, offset)

    def _rewrite_logic_error_path(self, error, offset=0):
        child_start = len(error.document_path) - offset

        for i, definition_errors in error.definitions_errors.items():
            if not definition_errors:
                continue

            nodename = '%s definition %s' % (error.rule, i)
            path = error.document_path + (nodename,)

            for child_error in definition_errors:
                rel_path = child_error.document_path[child_start:]
                child_error.document_path = path + rel_path

                self._rewrite_error_path(child_error, offset + 1)


class SchemaErrorHandler(BasicErrorHandler):
    messages = BasicErrorHandler.messages.copy()
    messages[0x03] = "unknown rule"
