package main

import (
	"fmt"
	"log"
	"os/exec"
	"strings"

	"github.com/spf13/cobra"
)

func main() {
	rootCmd := setupRootCmd()
	if err := rootCmd.Execute(); err != nil {
		log.Fatalf("Error executing command: %v", err)
	}
}

func setupRootCmd() *cobra.Command {
	var rootCmd = &cobra.Command{
		Use:   "tunnelmgr",
		Short: "Tunnel Manager is a CLI for managing VXLAN tunnels.",
	}

	rootCmd.AddCommand(createTunnelCmd(), listTunnelsCmd(), cleanupTunnelCmd())
	return rootCmd
}

func createTunnelCmd() *cobra.Command {
	var srcHost, dstHost, bridgeName, dev string
	var vni, srcPort, dstPort int

	cmd := &cobra.Command{
		Use:   "create",
		Short: "Create a VXLAN tunnel interface",
		Run: func(cmd *cobra.Command, args []string) {
			if err := createTunnel(vni, srcHost, dstHost, bridgeName, srcPort, dstPort, dev); err != nil {
				log.Fatalf("Failed to create tunnel: %v", err)
			}
			fmt.Println("Tunnel created successfully.")
		},
	}

	cmd.Flags().IntVar(&vni, "vni", 0, "VNI (Virtual Network Identifier)")
	cmd.Flags().StringVar(&srcHost, "src-host", "", "Source host IP address")
	cmd.Flags().StringVar(&dstHost, "dst-host", "", "Destination host IP address")
	cmd.Flags().StringVar(&bridgeName, "bridge-name", "", "Bridge name to associate with the tunnel interface")
	cmd.Flags().IntVar(&srcPort, "src-port", 4789, "Source port")
	cmd.Flags().IntVar(&dstPort, "dst-port", 4789, "Destination port")
	cmd.Flags().StringVar(&dev, "dev", "eth0", "Device")

	cmd.MarkFlagRequired("vni")
	cmd.MarkFlagRequired("src-host")
	cmd.MarkFlagRequired("dst-host")
	cmd.MarkFlagRequired("bridge-name")

	return cmd
}

func listTunnelsCmd() *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "List all tunnel interfaces",
		Run: func(cmd *cobra.Command, args []string) {
			if err := listTunnels(); err != nil {
				log.Fatalf("Failed to list tunnels: %v", err)
			}
		},
	}
}

func cleanupTunnelCmd() *cobra.Command {
	var vni int
	var bridgeName string

	cmd := &cobra.Command{
		Use:   "cleanup",
		Short: "Cleanup a tunnel interface",
		Run: func(cmd *cobra.Command, args []string) {
			if err := cleanupTunnel(vni, bridgeName); err != nil {
				log.Fatalf("Failed to cleanup tunnel: %v", err)
			}
			fmt.Println("Tunnel cleaned up successfully.")
		},
	}

	cmd.Flags().IntVar(&vni, "vni", 0, "VNI (Virtual Network Identifier)")
	cmd.Flags().StringVar(&bridgeName, "bridge-name", "", "Bridge name associated with the tunnel interface")

	cmd.MarkFlagRequired("vni")
	cmd.MarkFlagRequired("bridge-name")

	return cmd
}

func createTunnel(vni int, srcHost, dstHost, bridgeName string, srcPort, dstPort int, dev string) error {
	cmdStr := fmt.Sprintf("ip link add vxlan%d type vxlan id %d local %s remote %s dev %s dstport %d",
		vni, vni, srcHost, dstHost, dev, dstPort)
	if err := runCommand(cmdStr); err != nil {
		return err
	}

	upCmd := fmt.Sprintf("ip link set vxlan%d up", vni)
	if err := runCommand(upCmd); err != nil {
		return err
	}

	bridgeCmd := fmt.Sprintf("ip link set dev vxlan%d master %s", vni, bridgeName)
	return runCommand(bridgeCmd)
}

func cleanupTunnel(vni int, bridgeName string) error {
	bridgeCmd := fmt.Sprintf("ip link set dev vxlan%d nomaster", vni)
	if err := runCommand(bridgeCmd); err != nil {
		return err
	}

	delCmd := fmt.Sprintf("ip link del vxlan%d", vni)
	return runCommand(delCmd)
}

func listTunnels() error {
	return runCommand("ip -d link show type vxlan")
}

func runCommand(cmdStr string) error {
	cmdArgs := strings.Split(cmdStr, " ")
	cmd, args := cmdArgs[0], cmdArgs[1:]
	output, err := executor.Execute(cmd, args)
	if err != nil {
		return fmt.Errorf("command '%s' failed: %s, %v", cmdStr, output, err)
	}
	fmt.Print(output)
	return nil
}

type commandExecutor interface {
	Execute(cmd string, args []string) (string, error)
}

type systemCommandExecutor struct{}

func (e *systemCommandExecutor) Execute(cmd string, args []string) (string, error) {
	command := exec.Command(cmd, args...)
	output, err := command.CombinedOutput()
	return string(output), err
}

var executor commandExecutor = &systemCommandExecutor{}
