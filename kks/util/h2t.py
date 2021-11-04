from textwrap import wrap
from typing import Dict, Optional, List
import warnings

import html2text
from html2text import config
from html2text.utils import skipwrap, dumb_property_dict

__h2t_version__ = (2020, 1, 16)
if html2text.__version__ != __h2t_version__:
    ver = '.'.join(map(str, html2text.__version__))
    with warnings.catch_warnings():
        warnings.simplefilter("default")
        warnings.warn(ImportWarning(f"html2text {ver} may not be supported"))

TABLE_NOWRAP = "marker_for_disbling_wrap_in_tables"


def reformat_table(lines: List[str], right_margin: int) -> List[str]:
    """
    Given the lines of a table
    padds the cells and returns the new lines
    """
    # find the maximum width of the columns
    max_width = [len(x.rstrip()) + right_margin for x in lines[0].split("|")]
    max_cols = len(max_width)
    for line in lines:
        cols = [x.rstrip() for x in line.split("|")]
        num_cols = len(cols)

        # don't drop any data if colspan attributes result in unequal lengths
        if num_cols < max_cols:
            cols += [""] * (max_cols - num_cols)
        elif max_cols < num_cols:
            max_width += [len(x) + right_margin for x in cols[-(num_cols - max_cols) :]]
            max_cols = num_cols

        max_width = [
            max(len(x) + right_margin, old_len) for x, old_len in zip(cols, max_width)
        ]

# ====================modified====================
    max_width[0] = max_width[-1] = 0  # borders
# ====================!modified====================

    # reformat
    new_lines = []
    for line in lines:
        cols = [x.rstrip() for x in line.split("|")]
        if set(line.strip()) == set("-|"):
            filler = "-"
            new_cols = [
                x.rstrip() + (filler * (M - len(x.rstrip())))
                for x, M in zip(cols, max_width)
            ]
        else:
            filler = " "
            new_cols = [
                x.rstrip() + (filler * (M - len(x.rstrip())))
                for x, M in zip(cols, max_width)
            ]
        new_lines.append("|".join(new_cols))
    return new_lines


def pad_tables_in_text(text: str, right_margin: int = 1) -> str:
    """
    Provide padding for tables in the text
    """
    lines = text.split("\n")
    table_buffer = []  # type: List[str]
    table_started = False
    new_lines = []
    for line in lines:
        # Toggle table started
        if config.TABLE_MARKER_FOR_PAD in line:
            table_started = not table_started
            if not table_started:
                table = reformat_table(table_buffer, right_margin)
                new_lines.extend(table)
                table_buffer = []
                new_lines.append("")
            continue
        # Process lines
        if table_started:
            table_buffer.append(line)
        else:
            new_lines.append(line)
    return "\n".join(new_lines)


class HTML2Text(html2text.HTML2Text):
    """
    HTML2Text with table patch

    Added support for headless tables, disabled wrapping for long rows
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.headless_table = False
        self.bypass_tables = False
        self.ignore_tables = False
        self.tag_callback = self.custom_handler
        self.hidden = 0
        self.next_single_break = False

    def handle(self, data: str) -> str:
        self.feed(data)
        self.feed("")
        markdown = self.optwrap(self.finish())
        if self.pad_tables:
            return pad_tables_in_text(markdown)  # modified
        else:
            return markdown

    def custom_handler(
        self, _, tag: str, attrs: Dict[str, Optional[str]], start: bool
    ) -> bool:
        if tag == "sup":
            if start:
                self.o("^(")
            else:
                self.o(")")
            return True
        if tag == "div":
            if start:
                if self.hidden:
                    self.hidden += 1
                elif dumb_property_dict(attrs.get("style", "")).get("display") == "none":
                    self.hidden = 1
                    self.o("**[hidden text]**")
                    self.next_single_break = True
                    self.soft_br()
                    # NOTE maybe preceding_data should be modified here
                    return True

            elif not start and self.hidden:
                self.hidden -= 1
                if not self.hidden:
                    self.p_p = 0
                    self.space = False
                    self.soft_br()
                    self.o("**[end of hidden text]**")
                    self.p()
                    return True

        if tag not in ["table", "tr", "td", "th"]:
            return False

        if tag == "table":
            if start:
                self.table_start = True
# ====================modified====================
                self.o("<" + TABLE_NOWRAP + ">")
                self.o("  \n")
# ====================!modified====================
                if self.pad_tables:
                    self.o("<" + config.TABLE_MARKER_FOR_PAD + ">")
                    self.o("  \n")
            else:
                if self.pad_tables:
                    self.o("</" + config.TABLE_MARKER_FOR_PAD + ">")
                    self.o("  \n")
# ====================modified====================
                self.o("</" + TABLE_NOWRAP + ">")
                self.o("  \n")
# ====================!modified====================

        if tag in ["td", "th"] and start:
# ====================modified====================
            # save first row to temporary buffer
            if tag == 'td' and self.table_start:
                self.main_outtextlist = self.outtextlist
                self.outtextlist = []
                self.headless_table = True
                self.table_start = False
            self.o("| ")
            self.preceding_data = " "
            self.preceding_stressed = False
# ====================!modified====================

        if tag == "tr" and start:
            self.td_count = 0
        if tag == "tr" and not start:
# ====================modified====================
            if self.headless_table:
                # restore old textlist
                tr_textlist = self.outtextlist
                self.outtextlist = self.main_outtextlist
                del self.main_outtextlist
                # insert empty header
                # opening and closing bars are needed for correct compilation to html
                self.o("|{}|".format("|".join(["   "] * self.td_count)))
                self.soft_br()
                self.o("|{}|".format("|".join(["---"] * self.td_count)))
                self.o("\n")
                # add first row
                self.outtextlist += tr_textlist
                self.headless_table = False
            self.o("|")
# ====================!modified====================
            self.soft_br()
        if tag == "tr" and not start and self.table_start:
            # Underline table header
            self.o("|{}|".format("|".join(["---"] * self.td_count)))
            self.soft_br()
            self.table_start = False
        if tag in ["td", "th"] and start:
            self.td_count += 1
        return True

    def p(self) -> None:
        "Set pretty print to 1 or 2 lines"
        if self.next_single_break:  # for hidden text marker
            self.next_single_break = False
            self.p_p = 1
        else:
            self.p_p = 1 if self.single_line_break else 2

    def optwrap(self, text: str) -> str:
        """
        Wrap all paragraphs in the provided text.

        :type text: str

        :rtype: str
        """
        if not self.body_width:
            return text

        result = ""
        newlines = 0
# ====================modified====================
        in_table = False
# ====================!modified====================
        # I cannot think of a better solution for now.
        # To avoid the non-wrap behaviour for entire paras
        # because of the presence of a link in it
        if not self.wrap_links:
            self.inline_links = False
        for para in text.split("\n"):
            if len(para) > 0:
# ====================modified====================
                if TABLE_NOWRAP in para:
                    in_table = not in_table
                    continue
                if not skipwrap(para, self.wrap_links, self.wrap_list_items) and not in_table:
# ====================!modified====================
                    indent = ""
                    if para.startswith("  " + self.ul_item_mark):
                        # list item continuation: add a double indent to the
                        # new lines
                        indent = "    "
                    elif para.startswith("> "):
                        # blockquote continuation: add the greater than symbol
                        # to the new lines
                        indent = "> "
                    wrapped = wrap(
                        para,
                        self.body_width,
                        break_long_words=False,
                        subsequent_indent=indent,
                    )
                    result += "\n".join(wrapped)
                    if para.endswith("  "):
                        result += "  \n"
                        newlines = 1
                    elif indent:
                        result += "\n"
                        newlines = 1
                    else:
                        result += "\n\n"
                        newlines = 2
                else:
                    # Warning for the tempted!!!
                    # Be aware that obvious replacement of this with
                    # line.isspace()
                    # DOES NOT work! Explanations are welcome.
                    if not config.RE_SPACE.match(para):
                        result += para + "\n"
                        newlines = 1
            else:
                if newlines < 2:
                    result += "\n"
                    newlines += 1
        return result
