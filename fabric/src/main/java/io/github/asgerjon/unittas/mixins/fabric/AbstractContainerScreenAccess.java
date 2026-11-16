package io.github.asgerjon.unittas.mixins.fabric;

import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.inventory.Slot;
import org.spongepowered.asm.mixin.Mixin;
import org.spongepowered.asm.mixin.gen.Invoker;

/** A container screen's own click on a slot (protected in 26.3), as the mouse's is, for container.click. */
@Mixin(AbstractContainerScreen.class)
public interface AbstractContainerScreenAccess {

	@Invoker("slotClicked")
	void unittas$slotClicked(Slot slot, int slotId, int button, ContainerInput input);
}
