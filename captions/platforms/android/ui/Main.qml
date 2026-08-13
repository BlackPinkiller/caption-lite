import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: root
    width: 390
    height: 844
    visible: true
    color: "#151618"
    title: "Captions"

    component RoundAction: Button {
        id: action
        implicitHeight: 48
        leftPadding: 17
        rightPadding: 17
        font.pixelSize: 14
        font.weight: Font.Medium
        contentItem: Row {
            spacing: 7
            anchors.centerIn: parent
            Text {
                text: action.iconText
                color: action.primary ? "#18191c" : "#f1f2f3"
                font.pixelSize: 17
                anchors.verticalCenter: parent.verticalCenter
            }
            Text {
                text: action.text
                color: action.primary ? "#18191c" : "#f1f2f3"
                font: action.font
                anchors.verticalCenter: parent.verticalCenter
            }
        }
        background: Rectangle {
            radius: height / 2
            color: action.primary ? "#f1f2f3" : "#222428"
            border.width: action.primary ? 0 : 1
            border.color: "#44474d"
            opacity: action.down ? 0.78 : 1
        }
        property string iconText: ""
        property bool primary: false
    }

    ToolButton {
        id: settingsButton
        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: 7
        anchors.rightMargin: 9
        width: 42
        height: 42
        text: "⚙"
        font.pixelSize: 21
        Accessible.name: "设置"
        onClicked: settingsDrawer.open()
        background: Rectangle {
            radius: width / 2
            color: settingsButton.down ? "#292b2f" : "transparent"
        }
        contentItem: Text {
            text: settingsButton.text
            color: "#bec1c6"
            font: settingsButton.font
            horizontalAlignment: Text.AlignHCenter
            verticalAlignment: Text.AlignVCenter
        }
    }

    ListView {
        id: transcript
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: controls.top
        anchors.topMargin: 48
        anchors.leftMargin: 17
        anchors.rightMargin: 17
        anchors.bottomMargin: 13
        spacing: 10
        clip: true
        model: viewModel.sessionModel
        boundsBehavior: Flickable.StopAtBounds
        verticalLayoutDirection: ListView.TopToBottom
        property bool followCurrent: true
        onMovementStarted: followCurrent = atYEnd
        onMovementEnded: followCurrent = atYEnd
        onCountChanged: if (followCurrent) positionViewAtEnd()

        delegate: Rectangle {
            required property string source
            required property string translation
            required property bool current
            width: transcript.width
            height: copyColumn.implicitHeight + (current ? 16 : 0)
            radius: 10
            color: current ? "#24262a" : "transparent"

            Column {
                id: copyColumn
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                anchors.leftMargin: current ? 9 : 0
                anchors.rightMargin: current ? 9 : 0
                spacing: 2

                Text {
                    width: parent.width
                    visible: viewModel.displayMode !== "translation" && source.length > 0
                    text: source
                    wrapMode: Text.Wrap
                    color: current ? "#c9cbd0" : "#96999f"
                    font.family: viewModel.fontFamily
                    font.pixelSize: viewModel.sourceSize
                    lineHeight: 1.16
                }
                Text {
                    width: parent.width
                    visible: viewModel.displayMode !== "source" && translation.length > 0
                    text: translation
                    wrapMode: Text.Wrap
                    color: current ? "#ffffff" : "#96999f"
                    font.family: viewModel.fontFamily
                    font.pixelSize: viewModel.translationSize
                    font.weight: current ? Font.Medium : Font.Normal
                    lineHeight: 1.16
                }
            }
        }

        ScrollBar.vertical: ScrollBar {
            policy: transcript.moving && !transcript.atYEnd
                    ? ScrollBar.AsNeeded : ScrollBar.AlwaysOff
        }
    }

    Row {
        id: controls
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 18
        spacing: 9

        RoundAction {
            text: "麦克风"
            iconText: viewModel.microphoneEnabled ? "●" : "○"
            opacity: viewModel.microphoneEnabled ? 1 : 0.58
            onClicked: viewModel.toggleMicrophone()
        }
        RoundAction {
            text: viewModel.running ? "暂停" : "开始"
            iconText: viewModel.running ? "Ⅱ" : "▶"
            primary: true
            onClicked: viewModel.toggleRunning()
        }
    }

    Drawer {
        id: settingsDrawer
        edge: Qt.RightEdge
        width: Math.min(root.width * 0.9, 360)
        height: root.height
        modal: true
        background: Rectangle { color: "#1b1c1f" }

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Label {
                    text: "设置"
                    color: "#f4f4f5"
                    font.pixelSize: 19
                    font.weight: Font.Medium
                    Layout.fillWidth: true
                }
                ToolButton {
                    text: "关闭"
                    onClicked: settingsDrawer.close()
                }
            }
            Label { text: "识别"; color: "#f4f4f5"; font.weight: Font.Medium }
            Label { text: "Nemotron（默认）"; color: "#aeb1b6" }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#303237" }
            Label { text: "翻译"; color: "#f4f4f5"; font.weight: Font.Medium }
            Label { text: "翻译服务、语言与启用状态"; color: "#aeb1b6" }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#303237" }
            Label { text: "显示"; color: "#f4f4f5"; font.weight: Font.Medium }
            Label { text: "字体、字号、显示模式与悬浮字幕"; color: "#aeb1b6" }
            Rectangle { Layout.fillWidth: true; height: 1; color: "#303237" }
            Label { text: "高级"; color: "#f4f4f5"; font.weight: Font.Medium }
            Label { text: "模型、提示词与识别参数"; color: "#aeb1b6" }
            Item { Layout.fillHeight: true }
        }
    }
}
