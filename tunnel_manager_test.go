package main

import (
	"fmt"
	"testing"
)

type mockCommandExecutor struct{}

func (e *mockCommandExecutor) Execute(cmd string, args []string) (string, error) {
	return fmt.Sprintf("Executed %s with args %v", cmd, args), nil
}

func TestCreateTunnel(t *testing.T) {
	executor = &mockCommandExecutor{}

	defer func() { executor = &systemCommandExecutor{} }()

	err := createTunnel(100, "10.0.0.1", "10.0.0.2", "testBridge", 4789, 4789, "eth0")
	if err != nil {
		t.Fatalf("createTunnel failed: %v", err)
	}

}
