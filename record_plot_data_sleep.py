import sys
import time
import threading
import numpy as np
import configparser
import os

from PyQt5 import uic,QtWidgets
from PyQt5.QtWidgets import QApplication, QMessageBox
from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtCore import QRegExp

import data_collect
from data_cache import  data_queue
from utils import *
import scipy.io as sio


# 退出，保存数据并使得is_over=true
is_exit = False

# 运行状态
is_start = False

# 记录时间
record_time = 0

class MainWindow(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()

        # 从文件中加载UI定义
        self.ui = uic.loadUi("IR_UWB.ui")

        # 读取界面数值初始化
        self.ui.edit_partname.setText(getConfig("data","partname")) # 端口号初始值
        self.ui.edit_FPS.setText(getConfig("radar","fps"))          # FPS初始值
        self.ui.edit_run_time.setText(getConfig("data","run_time")) # 记录时间初始值
        self.ui.edit_interval.setText(getConfig("data","interval")) # 存储间隔初始值
        self.ui.checkBox_time.setChecked(True if getConfig("data","checkBox_time")=="True" else False)
        self.ui.checkBox_interval.setChecked(True if getConfig("data","checkBox_interval")=="True" else False)

        # 限制输入
        self.ui.edit_partname.setValidator(QRegExpValidator(QRegExp("[a-zA-Z0-9]{6}"),self))   # 只能输入字母和数字,限制6位
        self.ui.edit_FPS.setValidator(QRegExpValidator(QRegExp("[0-9]{3}"),self))   # 只能输入数字,限制3位
        self.ui.edit_run_time.setValidator(QRegExpValidator(QRegExp("[0-9]{5}"),self)) # 只能输入数字,限制5位
        self.ui.edit_interval.setValidator(QRegExpValidator(QRegExp("[0-9.]{5}"),self)) # 只能输入数字和".",限制5位

        # 计时器
        self.ui.record_text.setText("")

        # 按钮
        self.ui.button_start.clicked.connect(self.Start)    # 开始按钮
        self.ui.button_exit.clicked.connect(self.Exit)      # 结束按钮

        self.curve_init()


    def curve_init(self):

        global curve2,curve3,curve4,curve5,curve6

        # 图1：去除背景噪声（均值）快慢矩阵
        self.ui.widget_1.setWindowTitle('plot radar data')
        pg.setConfigOptions(antialias=True)
        colorMap = pg.colormap.get("CET-D1")
        range_ticks = [i for i in range(MAX_BIN - OFFSET + 1) if i % 10 == 0]
        time_ticks = [i for i in range(FRAMES + 1) if i % FPS == 0]
        p2 = self.ui.widget_1.addPlot(title="Normal Fast-slow Time Matrix (Removed Background Noise)")
        curve2 = pg.ImageItem()
        p2.addItem(curve2)
        p2.setLabels(left='time(s)', bottom='range(m)')
        bar2 = pg.ColorBarItem(values=(0, 1), colorMap="CET-D1")
        bar2.setImageItem(curve2)
        ax2 = p2.getAxis('bottom')
        ax2.setTicks([[(v, '{:.2f}'.format((v + OFFSET) * RANGE_RESOLUTION + RANGE_SATRT)) for v in range_ticks]])
        ax2 = p2.getAxis('left')
        ax2.setTicks([[(v, '{}'.format(int(v / FPS))) for v in time_ticks]])

        # 图2：每个距离对应Doppler偏移
        self.ui.widget_2.setWindowTitle('plot radar data')
        pg.setConfigOptions(antialias=True)
        colorMap = pg.colormap.get("CET-D1")
        range_ticks = [i for i in range(MAX_BIN - OFFSET + 1) if i % 10 == 0]
        time_ticks = [i for i in range(FRAMES + 1) if i % FPS == 0]
        p3 = self.ui.widget_2.addPlot(title="Distributed DFS")
        curve3 = pg.ImageItem()
        p3.addItem(curve3)
        p3.setLabels(left='doppler(Hz)', bottom='range(m)')
        bar3 = pg.ColorBarItem(values=(0, 1), colorMap="CET-D1")
        bar3.setImageItem(curve3)
        ax3 = p3.getAxis('bottom')
        ax3.setTicks([[(v, '{:.2f}'.format((v + OFFSET) * RANGE_RESOLUTION + RANGE_SATRT)) for v in range_ticks]])
        ax3 = p3.getAxis('left')
        freq_ticks = [i for i in range(NFFT + 1) if i % FPS == 0]
        ax3.setTicks([[(v, '{}'.format(int((v - NFFT / 2) * FPS / NFFT))) for v in freq_ticks]])

        # 图1：每1s钟所有距离点的Amplitude叠加值
        # self.ui.widget_3.setWindowTitle("1s钟所有距离点的Amplitude叠加值")
        p4 = self.ui.widget_3.addPlot(title="1s钟所有距离点的Amplitude叠加值")
        curve4 = p4.plot(pen='r')
        p4.setLabels(left='amplitude', bottom='range(m)')
        ax4 = p4.getAxis('bottom')
        ax4.setTicks([[(v, '{:.2f}'.format((v + OFFSET) * RANGE_RESOLUTION + RANGE_SATRT)) for v in range_ticks]])

        # 图2：每1s最大Amplitude对应距离点的I/Q复平面信号
        # self.ui.widget_4.setWindowTitle("最大Amplitude对应距离点的I/Q复平面信号")
        p5 = self.ui.widget_4.addPlot(title="最大Amplitude对应距离点的I/Q复平面信号")
        curve5 = p5.plot(pen='g')
        p5.setLabels(bottom='i', left='q')

        # 图3：最大Amplitude对应距离点的Amplitude时序序列变化
        # self.ui.widget_5.setWindowTitle("最大Amplitude对应距离点的Amplitude时序序列变化")
        p6 = self.ui.widget_5.addPlot(title="最大Amplitude对应距离点的Amplitude时序序列变化")
        curve6 = p6.plot(pen='b')
        p6.setLabels(left='amplitude', bottom='time(s)')
        ax6 = p6.getAxis('bottom')
        ax6.setTicks([[(v, '{}'.format(int(v / FPS))) for v in time_ticks]])


    def Start(self):
        
        global is_start,checkBox_time,checkBox_interval
        checkBox_time = self.ui.checkBox_time.isChecked()
        checkBox_interval = self.ui.checkBox_interval.isChecked()

        # 更改config文件中的数据
        WriteConfig("data","partname",self.ui.edit_partname.text())
        WriteConfig("radar","fps",self.ui.edit_FPS.text())
        WriteConfig("data","run_time",self.ui.edit_run_time.text())
        WriteConfig("data","interval",self.ui.edit_interval.text()) 
        WriteConfig("data","checkBox_time",str(checkBox_time))
        WriteConfig("data","checkBox_interval",str(checkBox_interval))

        # 判断能否启动
        global is_start
        if not self.main():
            if is_start:
                QMessageBox.critical(self.ui,'错误','程序已运行！')
            else:
                QMessageBox.critical(self.ui,'错误','端口错误或尚未连接！')
            return
        is_start = True

        # 创建一个新线程运行计时器
        threading.Thread(target=self.Record_time,args=[]).start()

    # 结束按键
    def Exit(self):
        global is_exit
        if is_start:
            is_exit = True
        time.sleep(0.5)
        self.ui.widget_1.clear()
        self.ui.widget_2.clear()
        self.curve_init()
        self.ui.record_text.setText("")



    def Record_time(self):      # 计时器界面                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        
        while is_start:
            if record_time < 60:
                self.ui.record_text.setText("Record data time %ds !" % record_time)
            elif record_time <3600:
                self.ui.record_text.setText("Record data time %dmin %ds !" % (int(record_time/60),record_time%60))
            else:
                min = int(record_time/60)
                self.ui.record_text.setText("Record data time %dh %dmin %ds !" % (int(min/60),int(min%60),record_time%60))
            time.sleep(0.3)


    def plot(self):
        # 参数设置
        partname = getConfig("data","partname")     # 端口号
        t = int(getConfig("data","run_time"))              # 数据记录时间(s)
        sample_rate = int(getConfig("radar","fps"))       # 样本采样率
        interval = int(float(getConfig("data","interval"))*60)    # 数据存储时间间隔
        t = 0 if checkBox_time else t                # t==0时，时间无穷
        interval = t if checkBox_interval else interval     # 时间和存储间隔都无穷时，值都为0

        # 开始时间
        starttime = time.strftime("%Y%m%d_%H%M%S", time.localtime())
        
        print("start plot")
        frecv = True
        datas = None
        datas1 = None

        # 计数器
        step = 0

        # 多线程下防止未保存数据就关闭
        is_over = False    # 关闭程序
        is_step = False

        while True:
            if data_queue.empty():
                time.sleep(0.01)
                continue
            else:
                # print("queue size:{}".format(data_queue.qsize()))
                data = data_queue.get()
                data = data.reshape(1,-1,2)

                if datas1 is None:
                    datas1 = data

                if frecv:
                    datas = data
                    frecv = False
                else:
                    datas = np.vstack((datas,data))
                    datas1 = np.vstack((datas1, data))
                datas_len = datas.shape[0]
                datas1_len = datas1.shape[0]

                if ((datas1_len % FPS) == 0):
                    global record_time
                    record_time = (datas1_len // FPS) + (step*interval)
                    print("Record data time {0}s !".format(record_time))
                    if(t > 0 and record_time > t):
                        global is_exit
                        is_exit = True
                
                if(datas_len >= FRAMES):
                    iq = datas[-FRAMES:,:,:]
                    org = iq[:,OFFSET:,0]+1j*iq[:,OFFSET:,1]
                    x = org[:,:]

                    #remove the background
                    iq_data = x - np.mean(x,0)
                    iq_abs = np.abs(iq_data)
                    iq_bin_sum = np.sum(iq_abs[-sample_rate:,:],0)

                    #determine the target bin
                    iq_bin = np.mean(np.abs(iq_data),0)
                    bin_offset = 0
                    bin_idx = np.where(np.max(iq_bin[bin_offset:]) <= iq_bin[bin_offset:])[0][0]
                    bin_idx += bin_offset
                    org_wave = iq_data[:,bin_idx]

                    #fft
                    fft_data = np.fft.fft(iq_data[-sample_rate:,:],n = NFFT,axis=0)
                    fft_shift_data = np.fft.fftshift(fft_data,axes=0)
                    fft_abs = np.abs(fft_shift_data)

                    #update plot data
                    #curve1.setImage(np.abs(x).T)
                    curve2.setImage(iq_abs.T)
                    curve3.setImage(fft_abs.T)
                    curve4.setData(iq_bin_sum)
                    curve5.setData(org_wave.real,org_wave.imag)
                    curve6.setData(iq_abs[:,bin_idx])

                    #update plot immediate
                    QtGui.QGuiApplication.processEvents()

                    # step = FPS
                    datas = datas[STEP:, :, :]

                # 存储数据
                if(interval > 0 and datas1_len >= sample_rate*interval):
                    is_step = True
                if (is_step or is_exit):
                    is_step = False
                    is_over = True if is_exit else False
                    iq1 = datas1[:, :, :]
                    org1 = iq1[:, OFFSET:, 0] + 1j * iq1[:, OFFSET:, 1]
                    x1 = org1[:, :]
                    endtime = time.strftime("%H%M%S", time.localtime())
                    file_name = "{0}_{1}.mat".format(starttime, endtime)
                    sio.savemat('./{}/{}'.format('Sleep_data', file_name), {'data': x1})
                    step = step + 1
                    datas1 = None

                # 退出
                if(t > 0 and step >= (t/interval)):
                    is_over = True
                if (is_over):
                    global is_start
                    print("{0} data finished!!".format(partname))
                    is_start = False
                    is_exit = False
                    is_over = False
                    data_collect.is_exit = True

                    # folder_path = "Sleep_data"
                    # # 获取文件夹中所有的mat文件名
                    # mat_files = [f for f in os.listdir(folder_path) if f.endswith(".mat")]
                    # mat_files.sort()
                    # print(mat_files)

                    # # 初始化一个空的列表，用于存储所有的二维数组
                    # data_list = []

                    # # 遍历每个mat文件
                    # for mat_file in mat_files:
                    #     # 拼接完整的文件路径
                    #     file_path = os.path.join(folder_path, mat_file)
                    #     # 加载mat文件中的"data"变量
                    #     data = sio.loadmat(file_path)["data"]
                    #     data_list.append(data)

                    # # 将列表中的所有二维数组沿着第一个轴（竖向）合并为一个大的二维数组
                    # merged_data = np.concatenate(data_list, axis=0)
                    # # 定义要保存的文件名
                    # save_file = folder_path + "\data.mat"
                    # # 保存合并后的二维数组为mat文件，变量名仍为"data"
                    # sio.savemat(save_file, {"data": merged_data})

                    sys.exit(0)
                
        return


    def main(self):
        FPS_change()
        # 定义一个全局的端口名称
        partname = getConfig("data","partname")
        recv = data_collect.SerialCollect(partname)
        if not recv.state:
            print("serial {0} init error.".format(partname))
            return False
        else:
            print('serial {0} success'.format(partname))


        collect = threading.Thread(target=recv.recv)
        collect.daemon = True
        collect.start()

        ##################
        threading.Thread(target=self.plot).start()

        '''
        timer = QtCore.QTimer()
        timer.timeout.connect(plot)
        timer.start(30)

        if (sys.flags.interactive != 1) or not hasattr(QtCore, 'PYQT_VERSION'):
            QtGui.QApplication.instance().exec_()
        '''
    
        return True

def getConfig(section, key):
    conf = configparser.ConfigParser()
    conf.read('./config.ini')
    return conf.get(section, key)

def WriteConfig(section,key,value):
    conf= configparser.ConfigParser()
    conf.read('./config.ini')
    conf.set(section,key,value)
    conf.write(open('./config.ini',"w"))

def FPS_change():
    global FPS
    FPS = int(getConfig("radar","fps"))


if __name__ == '__main__':

    if not os.path.exists("Sleep_data"):
        os.mkdir("Sleep_data")

    app = QApplication([])
    stats = MainWindow()
    stats.ui.show()
    app.exec_()



