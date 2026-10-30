import sys
import pandas as pd
import matplotlib

matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex, QVariant
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QTableView,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QSplitter,
    QToolBar,
    QFileDialog,
    QComboBox,
    QPushButton,
    QLabel,
    QFormLayout,
    QMessageBox,
    QInputDialog,
    QTabWidget,
    QHeaderView,
)

plt.rcParams["font.sans-serif"] = [
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "sans-serif",
]
plt.rcParams["axes.unicode_minus"] = False


class PandasModel(QAbstractTableModel):
    """Qt 表格模型，用于在 QTableView 中显示/编辑 pandas DataFrame"""

    def __init__(self, df: pd.DataFrame = None, parent=None):
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()

    def dataframe(self) -> pd.DataFrame:
        return self._df

    def set_dataframe(self, df: pd.DataFrame):
        self.beginResetModel()
        self._df = df
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df)

    def columnCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._df.columns)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return QVariant()
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            value = self._df.iat[index.row(), index.column()]
            if pd.isna(value):
                return ""
            return str(value)
        return QVariant()

    def setData(self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole) -> bool:
        if role != Qt.ItemDataRole.EditRole or not index.isValid():
            return False
        col = self._df.columns[index.column()]
        if str(value).strip() == "":
            value = None
        try:
            if pd.api.types.is_numeric_dtype(self._df[col]):
                value = float(value) if value is not None else None
            elif self._df[col].isna().all() and value is not None:
                try:
                    value = float(value)
                except (ValueError, TypeError):
                    pass
                else:
                    self._df[col] = pd.to_numeric(self._df[col], errors="coerce")
        except (ValueError, TypeError):
            return False
        self._df.iat[index.row(), index.column()] = value
        self.dataChanged.emit(index, index, [role])
        return True

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return QVariant()
        if orientation == Qt.Orientation.Horizontal:
            return str(self._df.columns[section]) if section < len(self._df.columns) else QVariant()
        return str(self._df.index[section]) if section < len(self._df.index) else QVariant()

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        base = super().flags(index)
        return base | Qt.ItemFlag.ItemIsEditable if index.isValid() else base


class MplCanvas(FigureCanvas):
    """matplotlib 画布，嵌入 Qt 界面"""

    def __init__(self, parent=None):
        self.fig = Figure(figsize=(5, 4), dpi=100)
        self.ax = self.fig.add_subplot(111)
        super().__init__(self.fig)
        self.setParent(parent)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("可视化数据分析表格")
        self.resize(1200, 800)

        self.model = PandasModel(self._sample_data())
        self._build_ui()
        self._build_toolbar()
        self.model.dataChanged.connect(lambda *_: self._refresh_stats())
        self.y_combo.currentIndexChanged.connect(lambda *_: self._refresh_stats())
        self._refresh_columns()
        self._refresh_stats()

    # ---------------- UI 构建 ----------------

    def _build_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧：表格
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setAlternatingRowColors(True)
        splitter.addWidget(self.table)

        # 右侧：标签页（统计 / 图表）
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.tabs = QTabWidget()
        right_layout.addWidget(self.tabs)

        # --- 统计页 ---
        stats_tab = QWidget()
        stats_layout = QVBoxLayout(stats_tab)
        stats_form = QFormLayout()
        self.stats_labels = {}
        for key, name in [
            ("count", "非空行数"),
            ("sum", "总和"),
            ("mean", "平均值"),
            ("median", "中位数"),
            ("max", "最大值"),
            ("min", "最小值"),
            ("std", "标准差"),
        ]:
            lbl = QLabel("—")
            self.stats_labels[key] = lbl
            stats_form.addRow(f"{name}:", lbl)
        stats_layout.addLayout(stats_form)
        self.stats_hint = QLabel("在“图表”页选择列后，此处显示该列统计信息")
        self.stats_hint.setStyleSheet("color: gray;")
        self.stats_hint.setWordWrap(True)
        stats_layout.addWidget(self.stats_hint)
        stats_layout.addStretch()
        self.tabs.addTab(stats_tab, "统计分析")

        # --- 图表页 ---
        chart_tab = QWidget()
        chart_layout = QVBoxLayout(chart_tab)
        chart_controls = QGridLayout()

        chart_controls.addWidget(QLabel("X 轴列:"), 0, 0)
        self.x_combo = QComboBox()
        chart_controls.addWidget(self.x_combo, 0, 1)

        chart_controls.addWidget(QLabel("Y 轴列(数值):"), 0, 2)
        self.y_combo = QComboBox()
        chart_controls.addWidget(self.y_combo, 0, 3)

        chart_controls.addWidget(QLabel("图表类型:"), 1, 0)
        self.chart_type = QComboBox()
        self.chart_type.addItems(["柱状图", "折线图", "饼图", "直方图"])
        chart_controls.addWidget(self.chart_type, 1, 1)

        self.plot_btn = QPushButton("生成图表")
        self.plot_btn.clicked.connect(self._plot)
        chart_controls.addWidget(self.plot_btn, 1, 2, 1, 2)

        chart_layout.addLayout(chart_controls)
        self.canvas = MplCanvas()
        chart_layout.addWidget(self.canvas)
        self.tabs.addTab(chart_tab, "图表可视化")

        splitter.addWidget(right_panel)
        splitter.setSizes([700, 500])
        self.setCentralWidget(splitter)

    def _build_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setMovable(False)
        self.addToolBar(toolbar)

        for text, slot in [
            ("打开 CSV", self.open_csv),
            ("保存 CSV", self.save_csv),
            ("添加行", self.add_row),
            ("删除选中行", self.remove_rows),
            ("添加列", self.add_column),
            ("示例数据", self.load_sample),
        ]:
            toolbar.addAction(text, slot)

    # ---------------- 数据操作 ----------------

    def _sample_data(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "月份": ["1月", "2月", "3月", "4月", "5月", "6月", "7月", "8月"],
                "销售额": [120, 200, 150, 260, 300, 280, 350, 400],
                "成本": [80, 130, 100, 160, 190, 170, 210, 250],
                "利润": [40, 70, 50, 100, 110, 110, 140, 150],
            }
        )

    def _current_df(self) -> pd.DataFrame:
        return self.model.dataframe()

    def _refresh_columns(self):
        df = self._current_df()
        cols = [str(c) for c in df.columns]
        numeric = [str(c) for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
        self.x_combo.clear()
        self.x_combo.addItems(cols)
        self.y_combo.clear()
        self.y_combo.addItems(numeric)
        if self.x_combo.count() > 0:
            self.x_combo.setCurrentIndex(0)
        if self.y_combo.count() > 0:
            self.y_combo.setCurrentIndex(0)

    def _refresh_stats(self):
        col = self.y_combo.currentText()
        df = self._current_df()
        if col and col in df.columns and pd.api.types.is_numeric_dtype(df[col]):
            s = df[col].dropna()
            values = {
                "count": f"{int(s.count())}",
                "sum": f"{s.sum():.4g}",
                "mean": f"{s.mean():.4g}",
                "median": f"{s.median():.4g}",
                "max": f"{s.max():.4g}",
                "min": f"{s.min():.4g}",
                "std": f"{s.std():.4g}" if s.count() > 1 else "—",
            }
            for k, v in values.items():
                self.stats_labels[k].setText(v)
            self.stats_hint.setText(f"当前统计列：{col}")
        else:
            for lbl in self.stats_labels.values():
                lbl.setText("—")
            self.stats_hint.setText("请选择一个数值列查看统计信息")

    # ---------------- 槽函数 ----------------

    def open_csv(self):
        path, _ = QFileDialog.getOpenFileName(self, "打开 CSV 文件", "", "CSV 文件 (*.csv);;所有文件 (*)")
        if not path:
            return
        try:
            try:
                df = pd.read_csv(path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(path, encoding="gbk")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法读取文件：\n{e}")
            return
        self.model.set_dataframe(df)
        self._refresh_columns()
        self._refresh_stats()

    def save_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "保存 CSV 文件", "data.csv", "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            self._current_df().to_csv(path, index=False, encoding="utf-8-sig")
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存失败：\n{e}")

    def add_row(self):
        df = self._current_df()
        self.model.set_dataframe(pd.concat([df, pd.DataFrame([{c: None for c in df.columns}])], ignore_index=True))
        self._refresh_stats()

    def remove_rows(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()}, reverse=True)
        if not rows:
            return
        df = self._current_df().drop(self._current_df().index[rows]).reset_index(drop=True)
        self.model.set_dataframe(df)
        self._refresh_stats()

    def add_column(self):
        name, ok = QInputDialog.getText(self, "添加列", "列名:")
        if not ok or not name.strip():
            return
        df = self._current_df().copy()
        df[name.strip()] = None
        self.model.set_dataframe(df)
        self._refresh_columns()

    def load_sample(self):
        self.model.set_dataframe(self._sample_data())
        self._refresh_columns()
        self._refresh_stats()

    def _plot(self):
        df = self._current_df()
        x_col = self.x_combo.currentText()
        y_col = self.y_combo.currentText()
        if not y_col:
            QMessageBox.information(self, "提示", "没有可用的数值列，请先加载或输入数据。")
            return

        self._refresh_stats()
        self.canvas.ax.clear()
        kind = self.chart_type.currentText()
        x = df[x_col].astype(str) if x_col else df.index.astype(str)
        y = df[y_col]

        try:
            if kind == "柱状图":
                self.canvas.ax.bar(x, y, color="#4C78A8")
            elif kind == "折线图":
                self.canvas.ax.plot(x, y, marker="o", color="#F58518")
            elif kind == "饼图":
                values = y.fillna(0).clip(lower=0)
                self.canvas.ax.pie(values, labels=x, autopct="%1.1f%%", startangle=90)
                self.canvas.ax.set_aspect("equal")
            elif kind == "直方图":
                self.canvas.ax.hist(y.dropna(), bins=10, color="#54A24B", edgecolor="white")
                self.canvas.ax.set_xlabel(y_col)
                self.canvas.ax.set_ylabel("频数")

            if kind != "饼图" and kind != "直方图":
                self.canvas.ax.set_xlabel(x_col)
                self.canvas.ax.set_ylabel(y_col)
            self.canvas.ax.set_title(f"{y_col} — {kind}")
            self.canvas.fig.tight_layout()
            self.canvas.draw()
        except Exception as e:
            QMessageBox.critical(self, "绘图错误", str(e))


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
