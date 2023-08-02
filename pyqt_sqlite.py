import math
import sys
import sqlite3
from sqlite3 import Error

import pandas as pd
from PyQt6 import uic
from PyQt6.QtCore import QAbstractTableModel, Qt
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import QMainWindow, QApplication, QMessageBox, QHeaderView, QAbstractItemView


class TableModel(QAbstractTableModel):
    def __init__(self, data):
        super(TableModel, self).__init__()
        self._data = data

    def data(self, index, role):
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._data.iloc[index.row(), index.column()]  # pandas' iloc method
            return str(value)

        if role == Qt.ItemDataRole.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignVCenter + Qt.AlignmentFlag.AlignHCenter

        if role == Qt.ItemDataRole.BackgroundRole and (index.row() % 2 == 0):
            return QColor('#d8ffdb')

    def rowCount(self, index):
        return self._data.shape[0]

    def columnCount(self, index):
        return self._data.shape[1]

    # Add Row and Column header
    def headerData(self, section, orientation, role):
        # section is the index of the column/row.
        if role == Qt.ItemDataRole.DisplayRole:  # more roles
            if orientation == Qt.Orientation.Horizontal:
                return str(self._data.columns[section])

            if orientation == Qt.Orientation.Vertical:
                return str(self._data.index[section])


class MainWindow(QMainWindow):
    UI = r'./pyqt_sqlite.ui'
    DATABASE = r'./Database/databaseAugment.sqlite'
    IMG_DIR = r'./Database/NIP2015_Images/'

    def __init__(self, *args, **kwargs):
        # Initialize UI
        super(MainWindow, self).__init__(*args, **kwargs)
        self.select_event_type = None
        uic.loadUi(self.UI, self)
        self.setWindowTitle('PyQt SQLite')

        # Set up tableview
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)  # row selection
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)  # single row select
        self.table.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        # Parameters of table page
        self.df = None
        self.total_row = 0
        self.total_page = 1
        self.current_page = 1

        # Create a database connect
        self.conn = create_connection(self.DATABASE)
        self.current_sql = ''
        self.queryTable()

        # Signals
        self.pBut_search.clicked.connect(self.queryTable)
        self.pBut_exit.clicked.connect(self.close)

        self.pBut_first_page.clicked.connect(self.loadFirstPage)
        self.pBut_previous_page.clicked.connect(self.loadPreviousPage)
        self.pBut_next_page.clicked.connect(self.loadNextPage)
        self.pBut_last_page.clicked.connect(self.loadLastPage)
        self.select_page.currentIndexChanged.connect(self.selectPage)
        self.spinBox_rows_per_page.valueChanged.connect(self.updateTable)

    def closeEvent(self, event):
        # Create a message box.
        messagebox = QMessageBox()
        messagebox.setWindowTitle('Message')
        messagebox.setText('Are you sure you want to exit the dialog?') # close window
        messagebox.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)

        # If user click "Yes", close the app.
        reply = messagebox.exec()
        if reply == QMessageBox.StandardButton.Yes:
            self.conn.close()  # close database
            event.accept()
        else:
            event.ignore()

    # Slots
    def queryTable(self):
        # Clear table content.
        self.clearTable()

        # Generate conditions of author.
        author = self.lineEdit_author.text().strip()
        if author == '':
            cond_author = "1 = 1"
        else:
            cond_author = f"Name LIKE '%{author}%'"

        # Generate conditions of keyword.

        keyword = self.lineEdit_keyword.text().strip()
        keyword_ranges = []
        if self.checkBox_title.isChecked():
            keyword_ranges.append('Title')
        if self.checkBox_abstract.isChecked():
            keyword_ranges.append('Abstract')
        if self.checkBox_paper_text.isChecked():
            keyword_ranges.append('PaperText')

        if keyword == '':
            cond_keyword = "1 = 1"
        elif len(keyword_ranges) == 0:  # No checkbox is checked
            dlg = QMessageBox(self)
            dlg.setWindowTitle('Warning')
            dlg.setText('請勾選關鍵字要搜尋的範圍！')
            dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
            dlg.setIcon(QMessageBox.Icon.Information)
            dlg.show()
            return
        else:
            cond_keyword = "( "
            for keyword_range in keyword_ranges:
                cond_keyword += f"{keyword_range} LIKE '%{keyword}%' OR "
            cond_keyword = cond_keyword[:-3] + ")"

        # Generate conditions of event type.
        event_type = self.select_event_type.currentText()
        if event_type == '不限':
            cond_event_type = "1 = 1"
        else:
            cond_event_type = f"EventType = '{event_type}'"

        # Generate SQL command.
        self.current_sql = f'''
            SELECT PaperId, Authors, EventType, Title, Abstract, PaperText, imgfile
            FROM "Papers"
            INNER JOIN
                (
                SELECT PaperAuthors.PaperId, group_concat(Authors.Name, ',') AS Authors
                FROM "PaperAuthors"
                INNER JOIN "Authors"
                ON PaperAuthors.AuthorId = Authors.Id
                WHERE {cond_author}
                GROUP BY PaperId
                )
            ON Papers.Id = PaperId
            WHERE {cond_event_type}
            AND {cond_keyword}
        '''

        # Execute.
        self.df = SQLExecute(self, self.current_sql)
        self.updateTable()

    def updateTable(self):
        if self.df is None:
            self.total_row = 0
            self.current_page = 1
            self.total_page = 1
        else:
            self.total_row = self.df.shape[0]
            self.current_page = 1
            self.total_page = math.ceil(self.total_row / self.get_rows_per_page())

        # Set up UI
        self.label_search_result.setText(f'總計: {self.total_row} 篇論文')
        self.label_total_page.setText(str(self.total_page))

        self.select_page.clear()
        for idx in range(1, self.total_page+1):
            self.select_page.addItem(str(idx))

        # Load the first page
        self.loadPage(self.current_page)

    def clearTable(self):
        if self.table.model() is not None:
            self.table.setModel(None)

        self.label_paper_id.setText('')
        self.label_title.setText('')
        self.label_author.setText('')
        self.label_event_type.setText('')
        self.pTextEdit_abstract.setPlainText('')
        self.pTextEdit_paper_text.setPlainText('')
        self.label_img.clear()
        self.label_img.setToolTip('')

    def loadPage(self, page_idx):
        self.clearTable()

        if self.df is None:
            return

        if page_idx < 1 or page_idx > self.total_page:  # Out of range.
            return

        self.current_page = page_idx
        self.select_page.setCurrentIndex(page_idx-1)

        # Calculate start row and end row
        start_row = (page_idx-1)*self.get_rows_per_page()
        end_row = start_row + self.get_rows_per_page()

        if end_row > self.total_row:
            end_row = self.total_row

        # Load data to table
        model = TableModel(self.df.iloc[start_row:end_row])
        self.table.setModel(model)

        # Resize the width of the column
        self.table.resizeColumnToContents(0)
        self.table.resizeColumnToContents(2)

        for column_hidden in [4, 5, 6]:  # Hide some columns (Abstract, PaperText, imgfile)
            self.table.hideColumn(column_hidden)

        # Connect current model with event (To display detail)
        selection_model = self.table.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(self.selectionChanged)

    def selectionChanged(self, selected, deselected):
        current_index = selected.indexes()[0]  # single selection
        row = current_index.row() + 1 + (self.current_page-1)*self.get_rows_per_page()

        if self.df is not None:
            self.label_paper_id.setText(str(self.df.loc[row]['PaperId']))
            self.label_title.setText(str(self.df.loc[row]['Title']))
            self.label_author.setText(str(self.df.loc[row]['Authors']))
            self.label_event_type.setText(str(self.df.loc[row]['EventType']))
            self.pTextEdit_abstract.setPlainText(str(self.df.loc[row]['Abstract']))
            self.pTextEdit_paper_text.setPlainText(str(self.df.loc[row]['PaperText']))
            self.label_img.setPixmap(QPixmap(str(self.IMG_DIR+self.df.loc[row]['imgfile'])))
            self.label_img.setToolTip(str(self.df.loc[row]['imgfile']))

    def loadFirstPage(self):
        if self.current_page != 1:
            self.loadPage(1)

    def loadPreviousPage(self):
        if self.current_page > 1:
            self.loadPage(self.current_page-1)

    def loadNextPage(self):
        if self.current_page < self.total_page:
            self.loadPage(self.current_page+1)

    def loadLastPage(self):
        if self.current_page != self.total_page:
            self.loadPage(self.total_page)

    def selectPage(self):
        try:
            page = int(self.select_page.currentText())
        except:
            return

        self.loadPage(page)

    def get_rows_per_page(self):
        return self.spinBox_rows_per_page.value()


def create_connection(db_file):
    """ create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :return: Connection object or None
    """
    conn = None
    try:
        conn = sqlite3.connect(db_file)
    except Error as e:
        print(e)

    return conn


def select_table(self, tbname):
    sql = 'select * from ' + tbname
    SQLExecute(self, sql)


def SQLExecute(self, SQL):
    """
    Execute a SQL command and display the requested items on the QTableView
    :param conn: SQL command
    :return: None
    """
    # Execute
    cur = self.conn.cursor()
    cur.execute(SQL)
    rows = cur.fetchall()

    if len(rows) == 0:  # nothing found
        # raise a messageBox here
        dlg = QMessageBox(self)
        dlg.setWindowTitle('SQL Information: ')
        dlg.setText('Nothing Found !!!')
        dlg.setStandardButtons(QMessageBox.StandardButton.Ok)
        dlg.setIcon(QMessageBox.Icon.Information)
        dlg.show()
        return

    # Process fetched output
    names = [description[0] for description in cur.description]  # extract column names
    self.df = pd.DataFrame(rows)
    self.df.index += 1  # shift index from 0 to 1
    self.df.columns = names

    return self.df


def main():
    app = QApplication(sys.argv)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
