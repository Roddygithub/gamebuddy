import QtQuick
import Quickshell.Io
import qs.Commons
import qs.Ui as Ui

// Omarchy bar widget: one icon that drives the GameBuddy widget over its CLI.
// The Python app owns the UI; this only toggles / pushes-to-talk.
Ui.BarWidget {
  id: root
  moduleName: "io.github.roddygithub.gamebuddy"

  property bool running: false
  property bool listening: false

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  function run(args) {
    proc.command = ["gamebuddy"].concat(args)
    proc.running = true
  }
  function toggle() { run(["toggle"]) }
  function ptt(action) { run(["ptt", action]) }
  function pickWindow() { run(["select-window"]) }

  Process {
    id: proc
    running: false
  }

  // Poll the socket-backed status so the icon reflects the real state.
  Process {
    id: statusProc
    command: ["gamebuddy", "status"]
    running: false
    stdout: StdioCollector {
      onStreamFinished: {
        try {
          const s = JSON.parse(text)
          root.running = !!s.ok
          root.listening = !!(s.recording || s.hands_free)
        } catch (e) {
          root.running = false
          root.listening = false
        }
      }
    }
  }
  Timer {
    interval: 3000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: statusProc.running = true
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
    text: root.listening ? "󰍬" : (root.running ? "󰍫" : "󰍭")
    tooltipText: root.running ? "GameBuddy — click to show/hide, right-click to pick the game window"
                              : "GameBuddy — click to start"
    onPressed: function(mouse) {
      if (mouse === Qt.RightButton) root.pickWindow()
      else if (root.running) root.toggle()
      else root.run([])
    }
  }
}
