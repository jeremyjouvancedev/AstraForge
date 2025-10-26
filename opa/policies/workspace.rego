package astraforge.workspace

default allow = false

allow {
  input.diff.size <= 5000
  endswith(input.diff.path, ".py")
}
