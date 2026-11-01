pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Effects
import Quickshell
import Quickshell.Io
import qs.Ui as Ui

// A lightweight shell controller. The separate Python engine owns voice and AI.
Ui.BarWidget {
  id: root
  moduleName: "io.github.roddygithub.gamebuddy"
  property bool running: false
  property bool installed: true
  property bool listening: false
  property bool opened: false
  property string model: ""
  readonly property string controlScript: decodeURIComponent(Qt.resolvedUrl("plugin-control.sh").toString().replace(/^file:\/\//, ""))

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function run(args) {
    if (control.running) return
    control.command = ["/bin/sh", root.controlScript].concat(args)
    control.running = true
  }
  function start() { Quickshell.execDetached(["/bin/sh", root.controlScript, "start"]) }
  function open() { if (running) run(["show"]); else start() }
  function close() { if (running) run(["hide"]) }
  function toggle() { if (running) run(["toggle"]); else start() }
  function ptt(action) { run(["ptt", action]) }
  function pickWindow() { run(["select-window"]) }

  Process {
    id: control
    onExited: { if (!statusProc.running) statusProc.running = true }
  }
  Process {
    id: statusProc
    command: ["/bin/sh", root.controlScript, "status"]
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          const state = JSON.parse(text)
          root.running = !!state.ok
          root.installed = state.installed !== false
          root.listening = !!(state.recording || state.hands_free)
          root.opened = !!state.visible
          root.model = state.model || ""
        } catch (error) {
          root.running = false
          root.listening = false
          root.opened = false
        }
      }
    }
  }
  Timer {
    interval: 5000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: { if (!statusProc.running) statusProc.running = true }
  }
  IpcHandler {
    target: "io.github.roddygithub.gamebuddy"
    function toggle(): void { root.toggle() }
    function pttStart(): void { root.ptt("start") }
    function pttStop(): void { root.ptt("stop") }
    function pickWindow(): void { root.pickWindow() }
  }
  Ui.BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    active: root.listening
    dimmed: !root.running
    iconComponent: Component {
      Item {
        Image {
          id: buddyImage
          anchors.fill: parent
          source: Qt.resolvedUrl("src/gamebuddy/assets/gamebuddy-symbolic.svg")
          sourceSize.width: Math.ceil(width * Screen.devicePixelRatio)
          sourceSize.height: Math.ceil(height * Screen.devicePixelRatio)
          visible: false
          layer.enabled: true
        }
        MultiEffect {
          anchors.fill: parent
          source: buddyImage
          colorization: 1.0
          colorizationColor: root.listening ? button.activeColor : button.foreground
        }
      }
    }
    tooltipText: !root.installed ? "GameBuddy — install the engine first (see README)"
      : root.running ? "GameBuddy — " + root.model + "\nClick: show/hide · Right-click: AI settings · Middle-click: game window"
      : "GameBuddy — click to start"
    onPressed: function(mouse) {
      if (mouse === Qt.RightButton && root.running) root.run(["ai-settings"])
      else if (mouse === Qt.MiddleButton && root.running) root.pickWindow()
      else root.toggle()
    }
  }
}
