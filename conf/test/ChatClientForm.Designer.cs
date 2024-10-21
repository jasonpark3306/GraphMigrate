using System.ComponentModel;
namespace GraphMigrate {
    partial class ChatClientForm
{

    private System.Windows.Forms.RichTextBox chatDisplay;
    private System.Windows.Forms.TextBox messageTextBox;
    private System.Windows.Forms.TextBox baseUrlTextBox;
    private System.Windows.Forms.Button sendButton;
    private System.Windows.Forms.Button sendImageButton;
    private System.Windows.Forms.Button setBaseUrlButton;



    private void InitializeComponent()
    {
        this.components = new System.ComponentModel.Container();
        this.chatDisplay = new System.Windows.Forms.RichTextBox();
        this.messageTextBox = new System.Windows.Forms.TextBox();
        this.baseUrlTextBox = new System.Windows.Forms.TextBox();
        this.sendButton = new System.Windows.Forms.Button();
        this.sendImageButton = new System.Windows.Forms.Button();
        this.setBaseUrlButton = new System.Windows.Forms.Button();

        // 
        // chatDisplay
        // 
        this.chatDisplay.Location = new System.Drawing.Point(12, 12);
        this.chatDisplay.Name = "chatDisplay";
        this.chatDisplay.Size = new System.Drawing.Size(460, 300);
        this.chatDisplay.TabIndex = 0;
        this.chatDisplay.Text = "";

        // 
        // messageTextBox
        // 
        this.messageTextBox.Location = new System.Drawing.Point(12, 318);
        this.messageTextBox.Name = "messageTextBox";
        this.messageTextBox.Size = new System.Drawing.Size(360, 23);
        this.messageTextBox.TabIndex = 1;

        // 
        // baseUrlTextBox
        // 
        this.baseUrlTextBox.Location = new System.Drawing.Point(12, 347);
        this.baseUrlTextBox.Name = "baseUrlTextBox";
        this.baseUrlTextBox.Size = new System.Drawing.Size(360, 23);
        this.baseUrlTextBox.TabIndex = 2;

        // 
        // sendButton
        // 
        this.sendButton.Location = new System.Drawing.Point(378, 318);
        this.sendButton.Name = "sendButton";
        this.sendButton.Size = new System.Drawing.Size(94, 23);
        this.sendButton.TabIndex = 3;
        this.sendButton.Text = "Send";
        this.sendButton.UseVisualStyleBackColor = true;

        // 
        // sendImageButton
        // 
        this.sendImageButton.Location = new System.Drawing.Point(378, 347);
        this.sendImageButton.Name = "sendImageButton";
        this.sendImageButton.Size = new System.Drawing.Size(94, 23);
        this.sendImageButton.TabIndex = 4;
        this.sendImageButton.Text = "Send Image";
        this.sendImageButton.UseVisualStyleBackColor = true;

        // 
        // setBaseUrlButton
        // 
        this.setBaseUrlButton.Location = new System.Drawing.Point(378, 376);
        this.setBaseUrlButton.Name = "setBaseUrlButton";
        this.setBaseUrlButton.Size = new System.Drawing.Size(94, 23);
        this.setBaseUrlButton.TabIndex = 5;
        this.setBaseUrlButton.Text = "Set Base URL";
        this.setBaseUrlButton.UseVisualStyleBackColor = true;

        // 
        // ChatClientForm
        // 
        this.AutoScaleDimensions = new System.Drawing.SizeF(7F, 15F);
        this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
        this.ClientSize = new System.Drawing.Size(484, 411);
        this.Controls.Add(this.chatDisplay);
        this.Controls.Add(this.messageTextBox);
        this.Controls.Add(this.baseUrlTextBox);
        this.Controls.Add(this.sendButton);
        this.Controls.Add(this.sendImageButton);
        this.Controls.Add(this.setBaseUrlButton);
        this.Name = "ChatClientForm";
        this.Text = "Chat Client";
        this.ResumeLayout(false);
        this.PerformLayout();
    }
}

}
