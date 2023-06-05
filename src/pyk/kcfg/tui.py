from __future__ import annotations
from enum import Enum, auto

from typing import TYPE_CHECKING, Union

from textual.app import App
from textual.containers import Horizontal, VerticalScroll
from textual.geometry import Offset, Region
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Footer, Static

from ..cterm import CTerm
from ..kast.inner import KApply, KRewrite
from ..kast.manip import flatten_label, minimize_term, push_down_rewrites
from ..kcfg import KCFG, KCFGShow
from ..prelude.kbool import TRUE
from ..utils import shorten_hashes, single

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from textual.app import ComposeResult
    from textual.events import Click

    from ..kast import KInner
    from ..ktool.kprint import KPrint


KCFGElem = Union[KCFG.Node, KCFG.Successor]


class GraphChunk(Static):
    _node_text: str

    class Selected(Message):
        chunk_id: str

        def __init__(self, chunk_id: str) -> None:
            self.chunk_id = chunk_id
            super().__init__()

    def __init__(self, id: str, node_text: Iterable[str] = ()) -> None:
        self._node_text = '\n'.join(node_text)
        super().__init__(self._node_text, id=id, classes='cfg-node')

    def on_enter(self) -> None:
        self.styles.text_opacity = '75%'  # type: ignore

    def on_leave(self) -> None:
        self.styles.text_opacity = None  # type: ignore

    def on_click(self, click: Click) -> None:
        self.post_message(GraphChunk.Selected(self.id or ''))
        click.stop()


class BehaviorView(Widget):
    _kcfg: KCFG
    _kprint: KPrint
    _minimize: bool
    _node_printer: Callable[[CTerm], Iterable[str]] | None
    _kcfg_nodes: Iterable[GraphChunk]

    def __init__(
        self,
        kcfg: KCFG,
        kprint: KPrint,
        nodes: Iterable[GraphChunk],
        minimize: bool = True,
        node_printer: Callable[[CTerm], Iterable[str]] | None = None,
        id: str = '',
    ):
        super().__init__(id=id)
        self._kcfg = kcfg
        self._kprint = kprint
        self._minimize = minimize
        self._node_printer = node_printer
        self._kcfg_nodes = nodes

    def compose(self) -> ComposeResult:
        return self._kcfg_nodes


class NodeView(Widget):
    _kprint: KPrint
    _custom_view: Callable[[KCFGElem], Iterable[str]] | None

    _element: KCFGElem | None

    _minimize: bool
    _term_on: bool
    _constraint_on: bool
    _custom_on: bool

    def __init__(
        self,
        kprint: KPrint,
        id: str = '',
        minimize: bool = True,
        term_on: bool = True,
        constraint_on: bool = True,
        custom_on: bool = False,
        custom_view: Callable[[KCFGElem], Iterable[str]] | None = None,
    ):
        super().__init__(id=id)
        self._kprint = kprint
        self._element = None
        self._minimize = minimize
        self._term_on = term_on
        self._constraint_on = constraint_on
        self._custom_on = custom_on or custom_view is not None
        self._custom_view = custom_view

    def _info_text(self) -> str:
        term_str = '✅' if self._term_on else '❌'
        constraint_str = '✅' if self._constraint_on else '❌'
        custom_str = '✅' if self._custom_on else '❌'
        minimize_str = '✅' if self._minimize else '❌'
        element_str = 'NOTHING'
        if type(self._element) is KCFG.Node:
            element_str = f'node({shorten_hashes(self._element.id)})'
        elif type(self._element) is KCFG.Edge:
            element_str = f'edge({shorten_hashes(self._element.source.id)},{shorten_hashes(self._element.target.id)})'
        elif type(self._element) is KCFG.Cover:
            element_str = f'cover({shorten_hashes(self._element.source.id)},{shorten_hashes(self._element.target.id)})'
        return f'{element_str} selected. {minimize_str} Minimize Output. {term_str} Term View. {constraint_str} Constraint View. {custom_str} Custom View.'

    def compose(self) -> ComposeResult:
        yield Horizontal(Static(self._info_text(), id='info'), id='info-view')
        yield Horizontal(Static('Term', id='term'), id='term-view', classes=('' if self._term_on else 'hidden'))
        yield Horizontal(
            Static('Constraint', id='constraint'),
            id='constraint-view',
            classes=('' if self._constraint_on else 'hidden'),
        )
        yield Horizontal(Static('Custom', id='custom'), id='custom-view', classes=('' if self._custom_on else 'hidden'))

    def toggle_option(self, field: str) -> bool:
        assert field in ['minimize', 'term_on', 'constraint_on', 'custom_on']
        field_attr = f'_{field}'
        old_value = getattr(self, field_attr)
        new_value = not old_value
        # Do not turn on custom view if it's not available
        if field == 'custom_on' and self._custom_view is None:
            new_value = False
        setattr(self, field_attr, new_value)
        self.query_one('#info', Static).update(self._info_text())
        self._update()
        return new_value

    def toggle_view(self, field: str) -> None:
        assert field in ['term', 'constraint', 'custom']
        if self.toggle_option(f'{field}_on'):
            self.query_one(f'#{field}-view', Horizontal).remove_class('hidden')
        else:
            self.query_one(f'#{field}-view', Horizontal).add_class('hidden')

    def update(self, element: KCFGElem, style: bool = False) -> None:
        self._element = element
        # if (style):
        #     self._focus_style()
        self._update()

    def _focus_style(self) -> None:
        # self.query_one('#node-view', NodeView).set_styles('border-left: double, red')
        # self.styles.border_left = None  # type: ignore
        # self.styles.border_left = ('double', 'red')  # type: ignore
        if self._element and type(self._element) is KCFG.Node:
            'node_' + str(self._element.id)
            # self.query_one(f'#{selected_chunk}', GraphChunk).set_styles('border-left: double, red')
            # self.query_one(f'#{selected_chunk}', GraphChunk)

    def _update(self) -> None:
        def _boolify(c: KInner) -> KInner:
            if type(c) is KApply and c.label.name == '#Equals' and c.args[0] == TRUE:
                return c.args[1]
            else:
                return c

        def _cterm_text(cterm: CTerm) -> tuple[str, str]:
            config = cterm.config
            constraints = map(_boolify, cterm.constraints)
            if self._minimize:
                config = minimize_term(config)
            return (self._kprint.pretty_print(config), '\n'.join(self._kprint.pretty_print(c) for c in constraints))

        term_str = 'Term'
        constraint_str = 'Constraint'
        custom_str = 'Custom'

        if self._element is not None:
            # TODO update the graph node style and remove any other existing style

            if type(self._element) is KCFG.Node:
                term_str, constraint_str = _cterm_text(self._element.cterm)
                # self._focus_style(self._element)

            elif type(self._element) is KCFG.Edge:
                config_source, *constraints_source = self._element.source.cterm
                config_target, *constraints_target = self._element.target.cterm
                constraints_new = [c for c in constraints_target if c not in constraints_source]
                config = push_down_rewrites(KRewrite(config_source, config_target))
                crewrite = CTerm(config, constraints_new)
                term_str, constraint_str = _cterm_text(crewrite)

            elif type(self._element) is KCFG.Cover:
                subst_equalities = map(_boolify, flatten_label('#And', self._element.csubst.subst.ml_pred))
                constraints = map(_boolify, flatten_label('#And', self._element.csubst.constraint))
                term_str = '\n'.join(self._kprint.pretty_print(se) for se in subst_equalities)
                constraint_str = '\n'.join(self._kprint.pretty_print(c) for c in constraints)

            elif type(self._element) is KCFG.Split:
                term_strs = [f'split: {shorten_hashes(self._element.source.id)}']
                for target_id, csubst in self._element.splits.items():
                    term_strs.append('')
                    term_strs.append(f'  - {shorten_hashes(target_id)}')
                    if len(csubst.subst) > 0:
                        subst_equalities = map(_boolify, flatten_label('#And', csubst.subst.ml_pred))
                        term_strs.extend(f'    {self._kprint.pretty_print(cline)}' for cline in subst_equalities)
                    if len(csubst.constraints) > 0:
                        constraints = map(_boolify, flatten_label('#And', csubst.constraint))
                        term_strs.extend(f'    {self._kprint.pretty_print(cline)}' for cline in constraints)
                term_str = '\n'.join(term_strs)

            elif type(self._element) is KCFG.NDBranch:
                term_strs = [f'ndbranch: {shorten_hashes(self._element.source.id)}']
                for target in self._element.targets:
                    term_strs.append('')
                    term_strs.append(f'  - {shorten_hashes(target.id)}')
                    term_strs.append('    (1 step)')
                term_str = '\n'.join(term_strs)

            if self._custom_view is not None:
                # To appease the type-checker
                if type(self._element) is KCFG.Node:
                    custom_str = '\n'.join(self._custom_view(self._element))
                elif type(self._element) is KCFG.Successor:
                    custom_str = '\n'.join(self._custom_view(self._element))

        self.query_one('#info', Static).update(self._info_text())
        self.query_one('#term', Static).update(term_str)
        self.query_one('#constraint', Static).update(constraint_str)
        self.query_one('#custom', Static).update(custom_str)


class Window(Enum):
    BEHAVIOR = 'behavior'
    TERM = 'term-view'
    CONSTRAINT = 'constraint-view'
    CUSTOM = 'custom-view'


class Direction(Enum):
    LEFT = 'h'
    DOWN = 'j'
    UP = 'k'
    RIGHT = 'l'

    @classmethod
    def dir_of(cls, key: str) -> Direction | None:
        match key:
            case 'h': return Direction.LEFT
            case 'j': return Direction.DOWN
            case 'k': return Direction.UP
            case 'l': return Direction.RIGHT
            case _: return None

class MoveKind(Enum):
    SINGLE = auto()
    PAGE = auto()
    CENTER = auto()
    BOUND = auto()


class KCFGViewer(App):
    CSS_PATH = 'style.css'

    _kcfg: KCFG
    _kprint: KPrint

    _node_printer: Callable[[CTerm], Iterable[str]] | None
    _custom_view: Callable[[KCFGElem], Iterable[str]] | None

    _minimize: bool

    _hidden_chunks: list[str]
    _selected_chunk: str | None

    _buffer: list[str]
    _node_ids: list[int]
    _node_idx: dict[int, int]
    _last_idx: int

    _curr_win: Window = Window.BEHAVIOR

    def __init__(
        self,
        kcfg: KCFG,
        kprint: KPrint,
        node_printer: Callable[[CTerm], Iterable[str]] | None = None,
        custom_view: Callable[[KCFGElem], Iterable[str]] | None = None,
        minimize: bool = True,
    ) -> None:
        super().__init__()
        self._kcfg = kcfg
        self._kprint = kprint
        self._node_printer = node_printer
        self._custom_view = custom_view
        self._minimize = minimize
        self._hidden_chunks = []
        self._buffer = []

        self._kcfg_nodes = []
        kcfg_show = KCFGShow(kprint)
        i = 0
        self._node_ids = []
        self._node_idx = {}
        for lseg_id, node_lines in kcfg_show.pretty_segments(
            self._kcfg, minimize=self._minimize, node_printer=self._node_printer
        ):
            self._kcfg_nodes.append(GraphChunk(lseg_id, node_lines))
            try:
                split = lseg_id.rsplit('_', 1)
                (name, count) = (split[0], split[1])
                if name == 'node':
                    as_id = int(count)
                    self._node_ids.append(as_id)
                    self._node_idx[as_id] = i
                    i += 1
            except:
                pass

        try:
            node_id = self._node_ids[0]
            self._selected_chunk = 'node_' + str(node_id)
            self._last_idx = self._node_idx[node_id]
        except:
            # TODO return an exception ?
            node_id = 0
            self._selected_chunk = None
            self._last_idx = 0

    def compose(self) -> ComposeResult:
        yield Horizontal(
            VerticalScroll(
                BehaviorView(
                    self._kcfg, self._kprint, nodes=self._kcfg_nodes, node_printer=self._node_printer, id='behavior'
                ),
                id='navigation',
            ),
            VerticalScroll(NodeView(self._kprint, custom_view=self._custom_view, id='node-view'), id='display'),
        )
        yield Footer()

    def on_mount(self) -> None:
        # TODO: update to see cells
        self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border-left: double red;')

    def on_graph_chunk_selected(self, message: GraphChunk.Selected) -> None:
        if message.chunk_id.startswith('node_'):
            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
            self._selected_chunk = message.chunk_id
            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border-left: double red;')
            node, *_ = message.chunk_id[5:].split('_')
            node_id = int(node)
            self._last_idx = self._node_idx[node_id]
            self.query_one('#node-view', NodeView).update(self._kcfg.node(node_id), True)

        elif message.chunk_id.startswith('edge_'):
            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
            # self._selected_chunk = None
            node_source, node_target, *_ = message.chunk_id[5:].split('_')
            source_id = int(node_source)
            target_id = int(node_target)
            edge = single(self._kcfg.edges(source_id=source_id, target_id=target_id))
            self.query_one('#node-view', NodeView).update(edge)

        elif message.chunk_id.startswith('cover_'):
            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
            # self._selected_chunk = None
            node_source, node_target, *_ = message.chunk_id[6:].split('_')
            source_id = int(node_source)
            target_id = int(node_target)
            cover = single(self._kcfg.covers(source_id=source_id, target_id=target_id))
            self.query_one('#node-view', NodeView).update(cover)

        elif message.chunk_id.startswith('split_'):
            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
            # self._selected_chunk = None
            node_source, node_target, *_ = message.chunk_id[6:].split('_')
            source_id = int(node_source)
            target_id = int(node_target)
            split = single(self._kcfg.splits(source_id=source_id, target_id=target_id))
            self.query_one('#node-view', NodeView).update(split)

        elif message.chunk_id.startswith('ndbranch_'):
            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
            # self._selected_chunk = None
            node_source, node_target, *_ = message.chunk_id[8:].split('_')
            source_id = int(node_source)
            target_id = int(node_target)
            ndbranch = single(self._kcfg.ndbranches(source_id=source_id, target_id=target_id))
            self.query_one('#node-view', NodeView).update(ndbranch)

    BINDINGS = [
        ('f', 'keystroke("f")', 'Fold node'),
        ('F', 'keystroke("F")', 'Unfold all nodes'),
        ('t', 'keystroke("term")', 'Toggle term'),
        ('c', 'keystroke("constraint")', 'Toggle constraint'),
        ('v', 'keystroke("custom")', 'Toggle custom'),
        ('m', 'keystroke("minimize")', 'Toggle minimization'),
        ('ctrl+w', 'keystroke("change-window")', 'Change window'),
        ('h', 'keystroke("h")', 'Go left'),
        ('j', 'keystroke("j")', 'Go down'),
        ('k', 'keystroke("k")', 'Go up'),
        ('l', 'keystroke("l")', 'Go right'),
        ('g', 'keystroke("g")', 'Go to start'),
        ('G', 'keystroke("G")', 'Go to end'),
        ('z', 'keystroke("z")', 'Center vertically'),
        ('ctrl+d', 'keystroke("page-down")', 'Page down'),
        ('ctrl+u', 'keystroke("page-up")', 'Page up'),
        # TODO: q for "quit"
    ]

    def focus_window(self, to: Window) -> None:
        curr_win = self._curr_win
        self.query_one(f'#{curr_win.value}').set_class(True, "deselected")
        self.query_one(f'#{to.value}').set_class(True, "selected")
        self._curr_win = to

    def move(self, dir: Direction, kind: MoveKind) -> None:
        view = self._curr_win.value
        match dir:
            case Direction.LEFT:
                match self._curr_win:
                    case Window.TERM | Window.CUSTOM | Window.CONSTRAINT:
                        self.query_one(f'#{view}', Horizontal).scroll_left(animate=False)
            case Direction.DOWN:
                if kind == MoveKind.SINGLE:
                    match self._curr_win:
                        case Window.BEHAVIOR:
                            if self._last_idx + 1 < len(self._node_ids):
                                idx = self._last_idx + 1
                                node_id = self._node_ids[idx]
                                self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
                                self._selected_chunk = 'node_' + str(node_id)
                                self._last_idx = idx
                                self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles(
                                    'border-left: double red;'
                                )
                                self.query_one('#node-view', NodeView).update(self._kcfg.node(node_id), True)
                        case Window.TERM | Window.CUSTOM | Window.CONSTRAINT:
                            self.query_one(f'#{view}', Horizontal).scroll_down(animate=False)
                elif kind == MoveKind.PAGE:
                    self.query_one(f'#{view}').scroll_page_down(animate=False)
                elif kind == MoveKind.BOUND:
                    if self._curr_win == Window.BEHAVIOR:
                        try:
                            node_id = self._node_ids[-1]
                            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
                            self._selected_chunk = 'node_' + str(node_id)
                            self._last_idx = self._node_idx[node_id]
                            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border-left: double red;')
                            self.query_one('#node-view', NodeView).update(self._kcfg.node(node_id), True)
                        except:
                            pass
                    else:
                        self.query_one(f'#{view}', Horizontal).scroll_end(animate=False)
                elif kind == MoveKind.CENTER:
                    if self._curr_win == Window.BEHAVIOR:
                        sel_node = self.query_one(f'#{self._selected_chunk}', GraphChunk)
                        bv = self.query_one('#behavior', BehaviorView)

                        central_point = Offset(
                            0,
                            sel_node.virtual_region.y + (1 + sel_node.virtual_region.height) // 2,
                        )

                        container_virtual_region = bv.virtual_region
                        target_region = Region(
                            0,
                            central_point.y - container_virtual_region.height // 2,
                            container_virtual_region.width,
                            container_virtual_region.height,
                        )
                        bv.scroll_to_region(target_region, animate=False)
            case Direction.UP:
                if kind == MoveKind.SINGLE:
                    match self._curr_win:
                        case Window.BEHAVIOR:
                            if kind == MoveKind.SINGLE:
                                if self._last_idx != 0:
                                    idx = self._last_idx - 1
                                    node_id = self._node_ids[idx]
                                    self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
                                    self._selected_chunk = 'node_' + str(node_id)
                                    self._last_idx = idx
                                    self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles(
                                        'border-left: double red;'
                                    )
                                    self.query_one('#node-view', NodeView).update(self._kcfg.node(node_id), True)
                        case Window.TERM | Window.CUSTOM | Window.CONSTRAINT:
                            self.query_one(f'#{view}', Horizontal).scroll_up(animate=False)
                elif kind == MoveKind.PAGE:
                    self.query_one(f'#{view}').scroll_page_up(animate=False)
                elif kind == MoveKind.BOUND:
                    if self._curr_win == Window.BEHAVIOR:
                        try:
                            node_id = self._node_ids[0]
                            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border: none;')
                            self._selected_chunk = 'node_' + str(node_id)
                            self._last_idx = 0
                            self.query_one(f'#{self._selected_chunk}', GraphChunk).set_styles('border-left: double red;')
                            self.query_one('#node-view', NodeView).update(self._kcfg.node(node_id), True)
                        except:
                            pass
                    else:
                        self.query_one(f'#{view}', Horizontal).scroll_home(animate=False)
            case Direction.RIGHT:
                match self._curr_win:
                    case Window.TERM | Window.CUSTOM | Window.CONSTRAINT:
                        self.query_one(f'#{view}', Horizontal).scroll_right(animate=False)

    async def action_keystroke(self, key: str) -> None:
        if key in ['h', 'j', 'k', 'l']:
            dir = Direction.dir_of(key)
            if dir is not None:
                if self._buffer and self._buffer[-1] in ['change-window']:
                    match dir:
                        case Direction.LEFT:
                            if self._curr_win != Window.BEHAVIOR:
                                self.focus_window(Window.BEHAVIOR)
                        case Direction.DOWN:
                            if self._curr_win == Window.TERM:
                                self.focus_window(Window.CONSTRAINT)
                            elif self._curr_win == Window.CONSTRAINT:
                                self.focus_window(Window.CUSTOM)
                        case Direction.UP:
                            if self._curr_win == Window.CUSTOM:
                                self.focus_window(Window.CONSTRAINT)
                            elif self._curr_win == Window.CONSTRAINT:
                                self.focus_window(Window.TERM)
                        case Direction.RIGHT:
                            if self._curr_win == Window.BEHAVIOR:
                                self.focus_window(Window.TERM)
                else:
                    self.move(dir, MoveKind.SINGLE)
        elif key == 'g':
            self.move(Direction.UP, MoveKind.BOUND)
        elif key == 'G':
            self.move(Direction.DOWN, MoveKind.BOUND)
        elif key == 'f':
            if self._selected_chunk is not None and self._selected_chunk.startswith('node_'):
                node_id = self._selected_chunk[5:]
                self._last_idx = self._node_idx[int(node_id)]
                self._hidden_chunks.append(self._selected_chunk)
                self.query_one(f'#{self._selected_chunk}', GraphChunk).add_class('hidden')
                self.query_one('#info', Static).update(f'HIDDEN: node({shorten_hashes(node_id)})')
        elif key == 'F':
            for hc in self._hidden_chunks:
                self.query_one(f'#{hc}', GraphChunk).remove_class('hidden')
            node_ids = [nid[5:] for nid in self._hidden_chunks]
            self.query_one('#info', Static).update(f'UNHIDDEN: nodes({shorten_hashes(node_ids)})')
            self._hidden_chunks = []
        elif key in ['term', 'constraint', 'custom']:
            self.query_one('#node-view', NodeView).toggle_view(key)
        elif key in ['minimize']:
            self.query_one('#node-view', NodeView).toggle_option(key)
        elif key == 'z':
            self.move(Direction.DOWN, MoveKind.CENTER)
        elif key == 'page-up':
            self.move(Direction.UP, MoveKind.PAGE)
        elif key == 'page-down':
            self.move(Direction.DOWN, MoveKind.PAGE)

        self._buffer = list()

        if key == 'change-window':
            self._buffer.append(key)
