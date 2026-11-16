package io.github.asgerjon.unittas.mixins.fabric;

import io.github.asgerjon.unittas.probe.FabricChat;
import net.minecraft.client.gui.components.ChatComponent;
import net.minecraft.client.multiplayer.chat.GuiMessageSource;
import net.minecraft.client.multiplayer.chat.GuiMessageTag;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.MessageSignature;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.injection.At;
import org.spongepowered.asm.mixin.injection.Inject;
import org.spongepowered.asm.mixin.injection.callback.CallbackInfo;

/** Every line the client's chat is given, a player's or the game's (ChatComponent.addMessage, where they all meet). */
@Mixin(ChatComponent.class)
public abstract class MixinChatComponent {

	@Inject(method = "addMessage", at = @At("HEAD"))
	private void unittas$heard(Component message, MessageSignature signature, GuiMessageSource source, GuiMessageTag tag,
		CallbackInfo info) {
		FabricChat.heard(message, source);
	}
}
