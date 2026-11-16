package io.github.asgerjon.unittas.mixins.fabric;

import net.minecraft.client.gui.components.CommandSuggestions;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.screens.ChatScreen;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Accessor;

/** The open chat's text box and its command suggestions, for chat.read. */
@Mixin(ChatScreen.class)
public interface ChatScreenAccess {

	@Accessor("input")
	EditBox unittas$input();

	@Accessor("commandSuggestions")
	CommandSuggestions unittas$suggestions();
}
