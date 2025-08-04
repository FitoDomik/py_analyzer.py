import os
import sys
import time
import json
import cProfile
import pstats
import io
import importlib
import re
import subprocess
import webbrowser
import argparse
import tempfile
import traceback
from datetime import datetime
from pathlib import Path
from collections import defaultdict
import importlib.util
import threading
from threading import Thread
if sys.platform == 'win32':
    import ctypes
    import locale
    if hasattr(sys, 'setdefaultencoding'):
        sys.setdefaultencoding('utf-8')  
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except AttributeError:
        pass
    locale.setlocale(locale.LC_ALL, 'ru_RU.UTF-8' if locale.getdefaultlocale()[0] == 'ru_RU' else '')
try:
    import psutil
    from jinja2 import Template
    import matplotlib
    matplotlib.use('Agg')  
    import matplotlib.pyplot as plt
    import pandas as pd
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
        QPushButton, QLabel, QFileDialog, QComboBox, QSpinBox, 
        QTabWidget, QTextEdit, QGroupBox, QFormLayout, QLineEdit,
        QProgressBar, QMessageBox, QCheckBox, QSplitter, QTreeWidget, 
        QTreeWidgetItem, QFrame
    )
    from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
    from PyQt6.QtGui import QIcon, QFont, QPixmap
    DEPENDENCIES_INSTALLED = True
except ImportError as e:
    DEPENDENCIES_INSTALLED = False
    MISSING_DEPENDENCY = str(e).split("'")[1] if "'" in str(e) else str(e)
class PyAnalyzer:
    def __init__(self, target_file, output_format='html', monitor_duration=10, custom_logger=None):
        self.target_file = Path(target_file)
        if not self.target_file.exists():
            raise FileNotFoundError(f"Файл {target_file} не найден")
        self.output_format = output_format.lower()
        self.monitor_duration = monitor_duration
        self.log = custom_logger if custom_logger else lambda x: None
        self.results = {
            'file_info': {
                'filename': self.target_file.name,
                'path': str(self.target_file.absolute()),
                'size': self.target_file.stat().st_size,
                'last_modified': datetime.fromtimestamp(self.target_file.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
            },
            'dependencies': {
                'imports': [],
                'packages': [],
                'versions': {}
            },
            'profiling': {
                'execution_time': 0,
                'function_stats': []
            },
            'resources': {
                'cpu': [],
                'memory': [],
                'disk': [],
                'network': []
            }
        }
    def run_analysis(self):
        try:
            self.analyze_dependencies()
            self.profile_code()
            self.monitor_resources()
            report_path = self.generate_report()
            return report_path
        except Exception as e:
            traceback.print_exc()
            raise
    def analyze_dependencies(self):
        try:
            if self._check_pipreqs_available():
                self._analyze_with_pipreqs()
            else:
                self._analyze_imports_statically()
        except Exception as e:
            self._analyze_imports_statically()
    def _check_pipreqs_available(self):
        try:
            import pipreqs
            return True
        except ImportError:
            return False
    def _analyze_with_pipreqs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir_path = Path(temp_dir)
            temp_file = temp_dir_path / self.target_file.name
            with open(self.target_file, 'r', encoding='utf-8', errors='replace') as src_file:
                content = src_file.read()
                with open(temp_file, 'w', encoding='utf-8') as dst_file:
                    dst_file.write(content)
            req_path = temp_dir_path / "requirements.txt"
            try:
                cmd = [sys.executable, "-m", "pipreqs", str(temp_dir_path), "--savepath", str(req_path), "--force"]
                process = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8')
                if process.returncode != 0:
                    raise Exception(f"pipreqs завершился с ошибкой: {process.stderr}")
                if req_path.exists():
                    with open(req_path, 'r', encoding='utf-8') as f:
                        requirements = f.readlines()
                    packages = []
                    versions = {}
                    for req in requirements:
                        req = req.strip()
                        if req:
                            if '>=' in req or '==' in req:
                                parts = re.split('>=|==', req)
                                package = parts[0].strip()
                                version = parts[1].strip()
                                packages.append(package)
                                versions[package] = version
                            else:
                                packages.append(req)
                    self.results['dependencies']['packages'] = packages
                    self.results['dependencies']['versions'] = versions
            except Exception:
                raise
    def _analyze_imports_statically(self):
        with open(self.target_file, 'r', encoding='utf-8', errors='replace') as f:
            content = f.read()
        import_patterns = [
            r'^\s*import\s+([a-zA-Z0-9_.,\s]+)',  
            r'^\s*from\s+([a-zA-Z0-9_.]+)\s+import',  
        ]
        imports = set()
        packages = set()
        for pattern in import_patterns:
            matches = re.findall(pattern, content, re.MULTILINE)
            for match in matches:
                for module in match.split(','):
                    module = module.strip()
                    if module:
                        base_module = module.split('.')[0]
                        imports.add(module)
                        packages.add(base_module)
        versions = {}
        for package in packages:
            try:
                if package not in sys.builtin_module_names and package != self.target_file.stem:
                    spec = importlib.util.find_spec(package)
                    if spec is not None:
                        try:
                            mod = importlib.import_module(package)
                            if hasattr(mod, '__version__'):
                                versions[package] = mod.__version__
                            elif hasattr(mod, 'VERSION'):
                                versions[package] = mod.VERSION
                            elif hasattr(mod, 'version'):
                                versions[package] = mod.version
                            else:
                                versions[package] = "неизвестно"
                        except:
                            versions[package] = "установлен"
            except:
                pass
        self.results['dependencies']['imports'] = list(imports)
        self.results['dependencies']['packages'] = list(packages)
        self.results['dependencies']['versions'] = versions 
    def profile_code(self):
        profiler = cProfile.Profile()
        try:
            original_dir = os.getcwd()
            os.chdir(self.target_file.parent)
            start_time = time.time()
            profiler.enable()
            spec = importlib.util.spec_from_file_location(
                self.target_file.stem, self.target_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            profiler.disable()
            execution_time = time.time() - start_time
            os.chdir(original_dir)
            s = io.StringIO()
            ps = pstats.Stats(profiler, stream=s).sort_stats('cumulative')
            ps.print_stats(20)  
            stats_lines = s.getvalue().split('\n')
            function_stats = []
            for line in stats_lines[5:]:
                if line.strip() and 'function calls' not in line:
                    parts = re.split(r'\s+', line.strip(), 5)
                    if len(parts) >= 5:
                        try:
                            stat = {
                                'ncalls': parts[0],
                                'tottime': float(parts[1]),
                                'percall': float(parts[2]),
                                'cumtime': float(parts[3]),
                                'percall_cumtime': float(parts[4]),
                                'filename_lineno_function': parts[5] if len(parts) > 5 else 'unknown'
                            }
                            function_stats.append(stat)
                        except (ValueError, IndexError):
                            continue
            self.results['profiling']['execution_time'] = execution_time
            self.results['profiling']['function_stats'] = function_stats
        except Exception as e:
            self.results['profiling']['execution_time'] = 0
            self.results['profiling']['error'] = str(e)
    def monitor_resources(self, duration=None, interval=0.5):
        if duration is None:
            duration = self.monitor_duration
        try:
            cmd = [sys.executable, str(self.target_file)]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            start_time = time.time()
            end_time = start_time + duration
            cpu_data = []
            memory_data = []
            disk_data = []
            network_data = []
            initial_disk_read, initial_disk_write = psutil.disk_io_counters().read_bytes, psutil.disk_io_counters().write_bytes
            initial_net_sent, initial_net_recv = psutil.net_io_counters().bytes_sent, psutil.net_io_counters().bytes_recv
            while time.time() < end_time and process.poll() is None:
                try:
                    p = psutil.Process(process.pid)
                    cpu_percent = p.cpu_percent(interval=0.1)
                    cpu_data.append({
                        'timestamp': time.time() - start_time,
                        'cpu_percent': cpu_percent
                    })
                    memory_info = p.memory_info()
                    memory_data.append({
                        'timestamp': time.time() - start_time,
                        'rss': memory_info.rss,  
                        'vms': memory_info.vms,  
                        'percent': p.memory_percent()
                    })
                    current_disk_read, current_disk_write = psutil.disk_io_counters().read_bytes, psutil.disk_io_counters().write_bytes
                    disk_data.append({
                        'timestamp': time.time() - start_time,
                        'read_bytes': current_disk_read - initial_disk_read,
                        'write_bytes': current_disk_write - initial_disk_write
                    })
                    initial_disk_read, initial_disk_write = current_disk_read, current_disk_write
                    current_net_sent, current_net_recv = psutil.net_io_counters().bytes_sent, psutil.net_io_counters().bytes_recv
                    network_data.append({
                        'timestamp': time.time() - start_time,
                        'bytes_sent': current_net_sent - initial_net_sent,
                        'bytes_recv': current_net_recv - initial_net_recv
                    })
                    initial_net_sent, initial_net_recv = current_net_sent, current_net_recv
                    time.sleep(interval)
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    break
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
            stdout, stderr = process.communicate()
            self.results['resources']['cpu'] = cpu_data
            self.results['resources']['memory'] = memory_data
            self.results['resources']['disk'] = disk_data
            self.results['resources']['network'] = network_data
            self.results['output'] = {
                'stdout': stdout.decode('utf-8', errors='replace'),
                'stderr': stderr.decode('utf-8', errors='replace'),
                'returncode': process.returncode
            }
        except Exception as e:
            self.results['resources']['error'] = str(e)
    def generate_report(self):
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        report_filename = f"report_{self.target_file.stem}_{timestamp}"
        if self.output_format == 'json':
            report_path = reports_dir / f"{report_filename}.json"
            with open(report_path, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, ensure_ascii=False, indent=2)
            return str(report_path)
        elif self.output_format == 'html':
            self._generate_graphs(reports_dir)
            html_template = self._get_html_template()
            formatted_data = self._format_data_for_report()
            template = Template(html_template)
            html_content = template.render(**formatted_data)
            report_path = reports_dir / f"{report_filename}.html"
            with open(report_path, 'w', encoding='utf-8') as f:
                f.write(html_content)
            return str(report_path)
        else:
            return None
    def _generate_graphs(self, reports_dir=None):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if reports_dir is None:
            reports_dir = Path(".")
        graphs_dir = reports_dir / f"graphs_{timestamp}"
        graphs_dir.mkdir(exist_ok=True)
        if self.results['resources']['cpu']:
            plt.figure(figsize=(10, 6))
            timestamps = [entry['timestamp'] for entry in self.results['resources']['cpu']]
            cpu_percent = [entry['cpu_percent'] for entry in self.results['resources']['cpu']]
            plt.plot(timestamps, cpu_percent)
            plt.title('Использование CPU')
            plt.xlabel('Время (сек)')
            plt.ylabel('CPU (%)')
            plt.grid(True)
            cpu_graph_path = graphs_dir / "cpu_usage.png"
            plt.savefig(cpu_graph_path)
            plt.close()
            self.results['graphs'] = self.results.get('graphs', {})
            self.results['graphs']['cpu'] = str(cpu_graph_path.absolute())
        if self.results['resources']['memory']:
            plt.figure(figsize=(10, 6))
            timestamps = [entry['timestamp'] for entry in self.results['resources']['memory']]
            memory_mb = [entry['rss'] / (1024 * 1024) for entry in self.results['resources']['memory']]
            plt.plot(timestamps, memory_mb)
            plt.title('Использование памяти')
            plt.xlabel('Время (сек)')
            plt.ylabel('Память (МБ)')
            plt.grid(True)
            memory_graph_path = graphs_dir / "memory_usage.png"
            plt.savefig(memory_graph_path)
            plt.close()
            self.results['graphs'] = self.results.get('graphs', {})
            self.results['graphs']['memory'] = str(memory_graph_path.absolute())
        if self.results['resources']['disk']:
            plt.figure(figsize=(10, 6))
            timestamps = [entry['timestamp'] for entry in self.results['resources']['disk']]
            disk_read = [entry['read_bytes'] / 1024 for entry in self.results['resources']['disk']]
            disk_write = [entry['write_bytes'] / 1024 for entry in self.results['resources']['disk']]
            plt.plot(timestamps, disk_read, label='Чтение')
            plt.plot(timestamps, disk_write, label='Запись')
            plt.title('Дисковая активность')
            plt.xlabel('Время (сек)')
            plt.ylabel('Данные (КБ)')
            plt.legend()
            plt.grid(True)
            disk_graph_path = graphs_dir / "disk_activity.png"
            plt.savefig(disk_graph_path)
            plt.close()
            self.results['graphs'] = self.results.get('graphs', {})
            self.results['graphs']['disk'] = str(disk_graph_path.absolute())
        if self.results['resources']['network']:
            plt.figure(figsize=(10, 6))
            timestamps = [entry['timestamp'] for entry in self.results['resources']['network']]
            net_sent = [entry['bytes_sent'] / 1024 for entry in self.results['resources']['network']]
            net_recv = [entry['bytes_recv'] / 1024 for entry in self.results['resources']['network']]
            plt.plot(timestamps, net_sent, label='Отправлено')
            plt.plot(timestamps, net_recv, label='Получено')
            plt.title('Сетевая активность')
            plt.xlabel('Время (сек)')
            plt.ylabel('Данные (КБ)')
            plt.legend()
            plt.grid(True)
            network_graph_path = graphs_dir / "network_activity.png"
            plt.savefig(network_graph_path)
            plt.close()
            self.results['graphs'] = self.results.get('graphs', {})
            self.results['graphs']['network'] = str(network_graph_path.absolute())
    def _format_data_for_report(self):
        data = {
            'file_info': self.results['file_info'],
            'dependencies': {
                'imports': self.results['dependencies']['imports'],
                'packages': [],
                'total_packages': len(self.results['dependencies']['packages'])
            },
            'profiling': {
                'execution_time': self.results['profiling']['execution_time'],
                'top_functions': []
            },
            'resources': {
                'cpu': {
                    'max': 0,
                    'avg': 0
                },
                'memory': {
                    'max': 0,
                    'avg': 0
                }
            },
            'graphs': self.results.get('graphs', {}),
            'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        for package in self.results['dependencies']['packages']:
            version = self.results['dependencies']['versions'].get(package, 'неизвестно')
            data['dependencies']['packages'].append({
                'name': package,
                'version': version
            })
        if self.results['profiling']['function_stats']:
            sorted_stats = sorted(
                self.results['profiling']['function_stats'],
                key=lambda x: x.get('cumtime', 0),
                reverse=True
            )
            data['profiling']['top_functions'] = sorted_stats[:10]
        if self.results['resources']['cpu']:
            cpu_values = [entry['cpu_percent'] for entry in self.results['resources']['cpu']]
            data['resources']['cpu']['max'] = max(cpu_values) if cpu_values else 0
            data['resources']['cpu']['avg'] = sum(cpu_values) / len(cpu_values) if cpu_values else 0
        if self.results['resources']['memory']:
            memory_values = [entry['rss'] / (1024 * 1024) for entry in self.results['resources']['memory']]  
            data['resources']['memory']['max'] = max(memory_values) if memory_values else 0
            data['resources']['memory']['avg'] = sum(memory_values) / len(memory_values) if memory_values else 0
        return data
    def _get_html_template(self):
        return """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Отчет анализа {{ file_info.filename }}</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            line-height: 1.6;
            margin: 0;
            padding: 20px;
            color: #333;
            background-color: #f8f8f8;
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            background-color: #fff;
            padding: 20px;
            box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);
        }
        .header {
            text-align: center;
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 2px solid #eee;
        }
        .section {
            margin-bottom: 30px;
            padding-bottom: 20px;
            border-bottom: 1px solid #eee;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        tr:hover {
            background-color: #f5f5f5;
        }
        .graph-container {
            display: flex;
            flex-wrap: wrap;
            justify-content: space-around;
            margin-top: 20px;
        }
        .graph {
            margin: 10px;
            text-align: center;
        }
        .graph img {
            max-width: 100%;
            height: auto;
            border: 1px solid #ddd;
        }
        .footer {
            text-align: center;
            margin-top: 30px;
            color: #777;
            font-size: 0.9em;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>Отчет анализа Python-программы</h1>
            <p><strong>Файл:</strong> {{ file_info.filename }}</p>
            <p><strong>Путь:</strong> {{ file_info.path }}</p>
            <p><strong>Размер:</strong> {{ file_info.size }} байт</p>
            <p><strong>Последнее изменение:</strong> {{ file_info.last_modified }}</p>
        </div>
        <div class="section">
            <h2>Зависимости</h2>
            <p>Всего найдено пакетов: {{ dependencies.total_packages }}</p>
            <h3>Установленные пакеты:</h3>
            <table>
                <thead>
                    <tr>
                        <th>Пакет</th>
                        <th>Версия</th>
                    </tr>
                </thead>
                <tbody>
                    {% for package in dependencies.packages %}
                    <tr>
                        <td>{{ package.name }}</td>
                        <td>{{ package.version }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <h3>Импорты в коде:</h3>
            <ul>
                {% for import_name in dependencies.imports %}
                <li>{{ import_name }}</li>
                {% endfor %}
            </ul>
        </div>
        <div class="section">
            <h2>Профилирование</h2>
            <p><strong>Общее время выполнения:</strong> {{ profiling.execution_time|round(4) }} секунд</p>
            <h3>Топ функций по времени выполнения:</h3>
            <table>
                <thead>
                    <tr>
                        <th>Вызовы</th>
                        <th>Общее время (сек)</th>
                        <th>Время на вызов (сек)</th>
                        <th>Накопленное время (сек)</th>
                        <th>Функция</th>
                    </tr>
                </thead>
                <tbody>
                    {% for func in profiling.top_functions %}
                    <tr>
                        <td>{{ func.ncalls }}</td>
                        <td>{{ func.tottime|round(6) }}</td>
                        <td>{{ func.percall|round(6) }}</td>
                        <td>{{ func.cumtime|round(6) }}</td>
                        <td>{{ func.filename_lineno_function }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        <div class="section">
            <h2>Использование ресурсов</h2>
            <div>
                <h3>CPU:</h3>
                <p><strong>Максимальное использование:</strong> {{ resources.cpu.max|round(2) }}%</p>
                <p><strong>Среднее использование:</strong> {{ resources.cpu.avg|round(2) }}%</p>
            </div>
            <div>
                <h3>Память:</h3>
                <p><strong>Максимальное использование:</strong> {{ resources.memory.max|round(2) }} МБ</p>
                <p><strong>Среднее использование:</strong> {{ resources.memory.avg|round(2) }} МБ</p>
            </div>
            <div class="graph-container">
                {% if graphs.cpu %}
                <div class="graph">
                    <h3>График использования CPU</h3>
                    <img src="file://{{ graphs.cpu }}" alt="График использования CPU">
                </div>
                {% endif %}
                {% if graphs.memory %}
                <div class="graph">
                    <h3>График использования памяти</h3>
                    <img src="file://{{ graphs.memory }}" alt="График использования памяти">
                </div>
                {% endif %}
                {% if graphs.disk %}
                <div class="graph">
                    <h3>График дисковой активности</h3>
                    <img src="file://{{ graphs.disk }}" alt="График дисковой активности">
                </div>
                {% endif %}
                {% if graphs.network %}
                <div class="graph">
                    <h3>График сетевой активности</h3>
                    <img src="file://{{ graphs.network }}" alt="График сетевой активности">
                </div>
                {% endif %}
            </div>
        </div>
        <div class="footer">
            <p>Отчет сгенерирован: {{ timestamp }}</p>
        </div>
    </div>
</body>
</html>
""" 
class AnalyzerWorker(QThread):
    progress_update = pyqtSignal(str)
    analysis_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    def __init__(self, target_file, output_format, duration, custom_logger=None):
        super().__init__()
        self.target_file = target_file
        self.output_format = output_format
        self.duration = duration
        self.custom_logger = custom_logger
    def run(self):
        try:
            def progress_logger(message):
                if self.custom_logger:
                    self.custom_logger(message)
                self.progress_update.emit(message)
            analyzer = PyAnalyzer(
                self.target_file, 
                output_format=self.output_format,
                monitor_duration=self.duration,
                custom_logger=progress_logger
            )
            report_path = analyzer.run_analysis()
            self.analysis_complete.emit(report_path)
        except Exception as e:
            self.error_occurred.emit(str(e))
class PyAnalyzerGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.recent_reports = []
        self.worker = None
        self.load_settings()
    def init_ui(self):
        self.setWindowTitle("PyAnalyzer - Анализатор Python-программ")
        self.setMinimumSize(800, 600)
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        main_layout = QVBoxLayout(self.central_widget)
        header = QLabel("PyAnalyzer")
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header_font = QFont()
        header_font.setPointSize(16)
        header_font.setBold(True)
        header.setFont(header_font)
        main_layout.addWidget(header)
        splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(splitter)
        top_widget = QWidget()
        top_layout = QVBoxLayout(top_widget)
        splitter.addWidget(top_widget)
        file_group = QGroupBox("Файл для анализа")
        file_layout = QHBoxLayout()
        self.file_path = QLineEdit()
        self.file_path.setReadOnly(True)
        self.file_path.setPlaceholderText("Выберите Python-файл для анализа...")
        browse_button = QPushButton("Обзор...")
        browse_button.clicked.connect(self.browse_file)
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(browse_button)
        file_group.setLayout(file_layout)
        top_layout.addWidget(file_group)
        settings_group = QGroupBox("Настройки анализа")
        settings_layout = QFormLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["HTML", "JSON"])
        settings_layout.addRow("Формат отчета:", self.format_combo)
        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(5, 60)
        self.duration_spin.setValue(10)
        self.duration_spin.setSuffix(" сек")
        settings_layout.addRow("Продолжительность мониторинга:", self.duration_spin)
        self.open_report_check = QCheckBox("Открыть отчет после завершения")
        self.open_report_check.setChecked(True)
        settings_layout.addRow("", self.open_report_check)
        settings_group.setLayout(settings_layout)
        top_layout.addWidget(settings_group)
        actions_layout = QHBoxLayout()
        self.run_button = QPushButton("Запустить анализ")
        self.run_button.setEnabled(False)  
        self.run_button.clicked.connect(self.run_analysis)
        self.cancel_button = QPushButton("Отменить")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_analysis)
        actions_layout.addWidget(self.run_button)
        actions_layout.addWidget(self.cancel_button)
        top_layout.addLayout(actions_layout)
        bottom_widget = QWidget()
        bottom_layout = QVBoxLayout(bottom_widget)
        splitter.addWidget(bottom_widget)
        self.tabs = QTabWidget()
        self.log_tab = QWidget()
        log_layout = QVBoxLayout(self.log_tab)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        log_layout.addWidget(self.log_text)
        self.tabs.addTab(self.log_tab, "Логи")
        self.reports_tab = QWidget()
        reports_layout = QVBoxLayout(self.reports_tab)
        self.reports_tree = QTreeWidget()
        self.reports_tree.setHeaderLabels(["Файл", "Дата", "Путь"])
        self.reports_tree.setColumnWidth(0, 200)
        self.reports_tree.setColumnWidth(1, 150)
        self.reports_tree.itemDoubleClicked.connect(self.open_report_from_tree)
        reports_layout.addWidget(self.reports_tree)
        reports_buttons_layout = QHBoxLayout()
        open_report_button = QPushButton("Открыть отчет")
        open_report_button.clicked.connect(self.open_selected_report)
        delete_report_button = QPushButton("Удалить отчет")
        delete_report_button.clicked.connect(self.delete_selected_report)
        reports_buttons_layout.addWidget(open_report_button)
        reports_buttons_layout.addWidget(delete_report_button)
        reports_layout.addLayout(reports_buttons_layout)
        self.tabs.addTab(self.reports_tab, "Отчеты")
        bottom_layout.addWidget(self.tabs)
        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setRange(0, 0)  
        self.progress_bar.hide()
        bottom_layout.addWidget(self.progress_bar)
        splitter.setSizes([300, 300])
    def browse_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Выберите Python-файл", "", "Python Files (*.py)"
        )
        if file_path:
            self.file_path.setText(file_path)
            self.run_button.setEnabled(True)
            self.statusBar().showMessage(f"Выбран файл: {file_path}")
    def run_analysis(self):
        target_file = self.file_path.text()
        if not target_file:
            QMessageBox.warning(
                self, "Предупреждение", 
                "Пожалуйста, выберите файл для анализа."
            )
            return
        if not os.path.isfile(target_file) or not target_file.endswith('.py'):
            QMessageBox.warning(
                self, "Предупреждение", 
                "Выбранный файл не существует или не является Python-файлом."
            )
            return
        reports_dir = Path("reports")
        if not reports_dir.exists():
            reports_dir.mkdir(exist_ok=True)
        output_format = self.format_combo.currentText().lower()
        duration = self.duration_spin.value()
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.show()
        self.tabs.setCurrentIndex(0)  
        self.log_text.clear()
        self.log(f"Начало анализа файла: {target_file}")
        self.log(f"Формат отчета: {output_format}")
        self.log(f"Продолжительность мониторинга: {duration} сек")
        self.log("-" * 80)
        self.worker = AnalyzerWorker(
            target_file, 
            output_format, 
            duration,
            custom_logger=self.log
        )
        self.worker.progress_update.connect(self.log)
        self.worker.analysis_complete.connect(self.analysis_completed)
        self.worker.error_occurred.connect(self.analysis_error)
        self.worker.start()
    def cancel_analysis(self):
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.log("Анализ отменен пользователем.")
            self.reset_ui_after_analysis()
    def log(self, message):
        self.log_text.append(message)
        self.log_text.verticalScrollBar().setValue(
            self.log_text.verticalScrollBar().maximum()
        )
    def analysis_completed(self, report_path):
        self.log(f"Анализ завершен. Отчет сохранен в: {report_path}")
        self.log("-" * 80)
        self.statusBar().showMessage(f"Анализ завершен: {report_path}")
        self.add_report_to_tree(report_path)
        if self.open_report_check.isChecked():
            self.open_report(report_path)
        self.tabs.setCurrentIndex(1)
        self.reset_ui_after_analysis()
    def analysis_error(self, error_message):
        self.log(f"Ошибка при анализе: {error_message}")
        self.log("-" * 80)
        self.statusBar().showMessage("Ошибка при анализе")
        QMessageBox.critical(
            self, "Ошибка", 
            f"Произошла ошибка при анализе:\n{error_message}"
        )
        self.reset_ui_after_analysis()
    def reset_ui_after_analysis(self):
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self.progress_bar.hide()
    def add_report_to_tree(self, report_path):
        try:
            path = Path(report_path)
            file_stat = path.stat()
            mod_time = datetime.fromtimestamp(file_stat.st_mtime)
            date_str = mod_time.strftime("%Y-%m-%d %H:%M:%S")
            item = QTreeWidgetItem([path.name, date_str, str(path)])
            self.reports_tree.insertTopLevelItem(0, item)
            self.reports_tree.setCurrentItem(item)
            self.recent_reports.insert(0, str(path))
            if len(self.recent_reports) > 20:
                self.recent_reports = self.recent_reports[:20]
            self.save_settings()
        except Exception:
            pass
    def load_reports_tree(self):
        self.reports_tree.clear()
        for report_path in self.recent_reports:
            try:
                path = Path(report_path)
                if path.exists():
                    file_stat = path.stat()
                    mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                    date_str = mod_time.strftime("%Y-%m-%d %H:%M:%S")
                    item = QTreeWidgetItem([path.name, date_str, str(path)])
                    self.reports_tree.addTopLevelItem(item)
            except Exception:
                continue
        reports_dir = Path("reports")
        if reports_dir.exists() and reports_dir.is_dir():
            for file_path in reports_dir.glob("report_*.html"):
                if str(file_path) not in self.recent_reports:
                    try:
                        file_stat = file_path.stat()
                        mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                        date_str = mod_time.strftime("%Y-%m-%d %H:%M:%S")
                        item = QTreeWidgetItem([file_path.name, date_str, str(file_path)])
                        self.reports_tree.addTopLevelItem(item)
                        self.recent_reports.append(str(file_path))
                    except Exception:
                        continue
            for file_path in reports_dir.glob("report_*.json"):
                if str(file_path) not in self.recent_reports:
                    try:
                        file_stat = file_path.stat()
                        mod_time = datetime.fromtimestamp(file_stat.st_mtime)
                        date_str = mod_time.strftime("%Y-%m-%d %H:%M:%S")
                        item = QTreeWidgetItem([file_path.name, date_str, str(file_path)])
                        self.reports_tree.addTopLevelItem(item)
                        self.recent_reports.append(str(file_path))
                    except Exception:
                        continue
            if len(self.recent_reports) > 20:
                self.recent_reports = self.recent_reports[:20]
            self.save_settings()
    def open_selected_report(self):
        selected_items = self.reports_tree.selectedItems()
        if selected_items:
            item = selected_items[0]
            report_path = item.text(2)  
            self.open_report(report_path)
    def open_report_from_tree(self, item, column):
        report_path = item.text(2)  
        self.open_report(report_path)
    def open_report(self, report_path):
        try:
            path = Path(report_path)
            if path.exists():
                webbrowser.open(f"file://{path.absolute()}")
                self.statusBar().showMessage(f"Отчет открыт: {report_path}")
            else:
                QMessageBox.warning(
                    self, "Предупреждение", 
                    f"Файл отчета не найден: {report_path}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка", 
                f"Ошибка при открытии отчета:\n{e}"
            )
    def delete_selected_report(self):
        selected_items = self.reports_tree.selectedItems()
        if not selected_items:
            return
        item = selected_items[0]
        report_path = item.text(2)  
        reply = QMessageBox.question(
            self, "Подтверждение", 
            f"Вы действительно хотите удалить отчет?\n{report_path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                path = Path(report_path)
                if path.exists():
                    os.remove(path)
                if report_path in self.recent_reports:
                    self.recent_reports.remove(report_path)
                index = self.reports_tree.indexOfTopLevelItem(item)
                self.reports_tree.takeTopLevelItem(index)
                self.save_settings()
                self.statusBar().showMessage(f"Отчет удален: {report_path}")
            except Exception as e:
                QMessageBox.critical(
                    self, "Ошибка", 
                    f"Ошибка при удалении отчета:\n{e}"
                )
    def save_settings(self):
        try:
            settings_dir = Path.home() / ".py_analyzer"
            settings_dir.mkdir(exist_ok=True)
            settings_file = settings_dir / "settings.txt"
            with open(settings_file, "w", encoding="utf-8", errors='replace') as f:
                f.write(f"format={self.format_combo.currentText().lower()}\n")
                f.write(f"duration={self.duration_spin.value()}\n")
                f.write(f"open_report={int(self.open_report_check.isChecked())}\n")
                f.write("recent_reports=\n")
                for report in self.recent_reports:
                    f.write(f"{report}\n")
        except Exception:
            pass
    def load_settings(self):
        try:
            settings_file = Path.home() / ".py_analyzer" / "settings.txt"
            if not settings_file.exists():
                return
            with open(settings_file, "r", encoding="utf-8", errors='replace') as f:
                lines = f.readlines()
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    if line.startswith("format="):
                        format_value = line.split("=", 1)[1].upper()
                        index = self.format_combo.findText(format_value)
                        if index >= 0:
                            self.format_combo.setCurrentIndex(index)
                    elif line.startswith("duration="):
                        try:
                            duration = int(line.split("=", 1)[1])
                            self.duration_spin.setValue(duration)
                        except ValueError:
                            pass
                    elif line.startswith("open_report="):
                        try:
                            open_report = bool(int(line.split("=", 1)[1]))
                            self.open_report_check.setChecked(open_report)
                        except ValueError:
                            pass
                    elif line == "recent_reports=":
                        self.recent_reports = []
                    elif self.recent_reports is not None:
                        self.recent_reports.append(line)
            self.load_reports_tree()
        except Exception:
            pass
    def closeEvent(self, event):
        self.save_settings()
        if self.worker and self.worker.isRunning():
            reply = QMessageBox.question(
                self, "Подтверждение", 
                "Анализ все еще выполняется. Вы уверены, что хотите выйти?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                self.worker.terminate()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()
def check_and_install_dependencies():
    if DEPENDENCIES_INSTALLED:
        return True
    response = input(f"Отсутствует {MISSING_DEPENDENCY}. Установить зависимости? (y/n): ").strip().lower()
    if response != 'y':
        return False
    try:
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "PyQt6", "psutil", "matplotlib", "pandas", "jinja2", "pipreqs"
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.execv(sys.executable, [sys.executable] + sys.argv)
    except subprocess.CalledProcessError:
        return False
    return True
def main():
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    parser = argparse.ArgumentParser(description='PyAnalyzer - Анализатор Python-программ')
    parser.add_argument('file', nargs='?', help='Путь к анализируемому Python-файлу')
    parser.add_argument('--gui', action='store_true', help='Запустить графический интерфейс')
    parser.add_argument('--format', choices=['html', 'json'], default='html', 
                        help='Формат выходного отчета (html, json)')
    parser.add_argument('--duration', type=int, default=10, 
                        help='Продолжительность мониторинга ресурсов в секундах')
    args = parser.parse_args()
    if not args.file and not args.gui:
        args.gui = True
    if not check_and_install_dependencies():
        return 1
    if args.gui:
        app = QApplication(sys.argv)
        app.setStyle('Fusion')  
        window = PyAnalyzerGUI()
        window.show()
        return app.exec()
    else:
        try:
            file_path = Path(args.file)
            if not file_path.exists() or not file_path.is_file():
                return 1
            analyzer = PyAnalyzer(
                args.file,
                output_format=args.format,
                monitor_duration=args.duration
            )
            report_path = analyzer.run_analysis()
            if report_path and args.format == 'html':
                if input("Открыть отчет? (y/n): ").strip().lower() == 'y':
                    webbrowser.open(f"file://{Path(report_path).absolute()}")
            return 0
        except Exception:
            return 1
if __name__ == "__main__":
    sys.exit(main())
