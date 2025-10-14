// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

contract ReportGenerator {
    address payable public owner;
    uint256 public reportFee = 1 * 10**18; // 1 MATIC (18 decimals)

    event ReportPaid(address indexed user, uint256 amount);

    constructor() {
        owner = payable(msg.sender);
    }

    function generateReport() public payable {
        require(msg.value == reportFee, "Incorrect fee sent.");

        // Transfer the fee to the owner
        (bool success, ) = owner.call{value: msg.value}("");
        require(success, "Failed to send funds");

        // Emit an event to log the payment
        emit ReportPaid(msg.sender, msg.value);
    }
}